"""model/services/world_query_assistant.py — 回答玩家关于自身状态/所在地点/
世界地图的元问题（"我在哪里""离我最近的城市有哪些"这类），用真正的 function
calling（llm_tool_loop.py + game_context_tools.py）取真实数据作答，不许凭空
编造地名/数值。

跟 live_content_author.py 是同一层级的"对局中能碰大模型"的例外（README §1.12/
§1.13）：但这里只读，不创造新的 GameEventDef/Location，不改存档、不消耗回合、
不进 AgentEventHistory——语义上跟 inspect_npc/scan 这两个既有只读查询命令一样，
由 ChatController 在两段式循环之外直接调用。
"""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Protocol

from model.services.game_context_tools import build_tool_impls, build_tool_specs
from model.services.llm_tool_loop import run_tool_loop

if TYPE_CHECKING:
    from model.domain.agent import Agent
    from model.domain.map import WorldView

_logger = logging.getLogger("eventhorizon.world_query_assistant")

_SYSTEM_PROMPT = (
    "你是一款文字修仙游戏里的向导，只负责回答玩家关于自己状态、当前所在地、"
    "世界地图的问题（比如「我在哪里」「离我最近的城市有哪些」「我现在是什么境界」）。\n"
    "规则：\n"
    "1. 回答前必须先调用提供的工具获取真实数据，绝不能凭空编造地名、数值、"
    "方位——工具没查到的信息就说不知道，不能猜。\n"
    '2. 如果玩家这句话根本不是在问这类信息（比如是想执行一个游戏动作、闲聊、'
    '或者完全无关的话），只输出 {"not_info_query": true}，不要调用工具、不要'
    "编回答，也不要有任何其他文字。\n"
    "3. 确认是在问这类问题时，用一两句自然的第二人称白话回答，不要输出 JSON、"
    "不要罗列原始字段名。\n"
    "4. list_reachable_locations 返回的是「从当前位置能去的其他地方」，不包含"
    "玩家现在就站着的这个地点本身——回答「附近/可达的城市有哪些」时，只报告这个"
    "列表里的地点，不要把玩家当前所在地也算进「附近有哪些」的答案里（可以在回答"
    "开头提一句「你现在在 XX」当背景，但那不算在「附近」的列表里）。\n"
    "5. list_reachable_locations 里同一个地点所在城市内部的子地点（集市、主街、"
    "城门、酒楼、当铺这类 location_type 不是「城市」的）跟真正另一座城市/山门/"
    "秘境是混在一起返回的——玩家问的是「附近有哪些城市」这种限定了类型的问题时，"
    "只挑 location_type 正好等于玩家问的那个类型（比如「城市」）的地点回答，不要"
    "不加区分地把所有类型都列出来；玩家问的是「附近有什么地方/能去哪」这种不限"
    "类型的开放问题，才把整个列表都说出来。"
)

# 触发这次问答尝试的关键词——只是"值得问一下"的便宜本地预筛，精确判断交给上面
# 第 2 条规则里的 LLM 自己决定；命中了不代表一定会被采纳为信息问答，助手判断
# 出「不是」或者调用失败，调用方（chat_controller.py）都会原样回落到正常的两段
# 式命令解析流程，不会因为这里猜错了就把一句正常的游戏指令截胡。
_INFO_QUESTION_KEYWORDS = (
    "我在哪", "这是哪", "什么地方", "在什么地方", "身处何处", "哪个城市",
    "最近的城市", "附近的城市", "附近有哪些", "周围有什么", "周围有哪些",
    "有哪些地方", "哪些地方可以去", "能去哪些地方", "世界地图",
    "我的状态", "我是什么境界", "我现在什么境界", "我还有多少钱", "我几岁了",
    "现在什么时候", "现在几点", "现在是什么时辰",
)


def looks_like_info_question(raw_text: str) -> bool:
    return any(keyword in raw_text for keyword in _INFO_QUESTION_KEYWORDS)


class LlmClient(Protocol):
    def complete_with_tools(self, messages: list[dict], tools: list[dict]) -> dict: ...


class WorldQueryAssistant:
    def __init__(self, client: LlmClient) -> None:
        self._client = client

    def answer(self, agent: "Agent", world: "WorldView", player_text: str) -> str | None:
        """能确认是在问信息、也答上来了，返回文案；判断这句话其实不是在问信息，
        或者过程中出错，返回 None——调用方拿到 None 时原样回落到正常的两段式
        命令解析流程，这不是这个助手的职责范围。"""
        tools = build_tool_specs()
        tool_impls = build_tool_impls(agent, world)
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": player_text},
        ]
        content = run_tool_loop(self._client, messages, tools, tool_impls)
        if content is None or _declines(content):
            return None
        return content.strip()


def _declines(content: str) -> bool:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return False
    return isinstance(parsed, dict) and bool(parsed.get("not_info_query"))
