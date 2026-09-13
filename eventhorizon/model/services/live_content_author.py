"""model/services/live_content_author.py — 对局中解析失败兜底专用的实时创作
能力：规则解析器（chat_parser.py）和向量兜底（matching.py::find_best_matching_
command）都处理不了玩家这句话时，最后一层退路——调用大模型理解意图，创作出的
内容立即落库生效，不经过草稿/人工发布。

这是 README §1.12"对局隔离"的一次有意识例外，用户已明确要求、明确知晓后果
（会绕开 validate_event_def 的联动校验之外的一切人工审核）。跟另外两种已有的
"对局里能碰大模型"的用法都不是一回事：

  - LlmAuthorPort（model/services/ports.py）：仅限录入侧（admin_controller.py），
    产出草稿、需要人工审核发布才生效——test_layering.py 的
    PlayPathIsolationFromLlmAuthorTests 继续正确地禁止它出现在
    play_turn.py/matching.py/chat_parser.py，这条边界没有变。
  - live_narrative_writer.py（LlmEventWriter）：只补一句缺失的叙事文案，不创造
    新的 GameEventDef/Location，落库的是"补全"不是"新增"。
  - 这里（LiveContentAuthor）：明确会创造全新的 GameEventDef / Location / Route
    并立即生效——三者用途、风险、落库时机都不一样，改一个不要照抄另一个的假设。

安全边界（不是"完全不设防"，而是"不做人工审核，但仍然过自动校验/先核实数据/
先问清楚"）：
  - 事件创作的 result_pool 只放开 state_change（跟 LlmEventFlavorAuthor 同一套
    安全过滤），没有 item_drop/chain_event 这类会悬空引用的类型。
  - 地点创作的 kind 必须落在 LocationKind 白名单内。
  - 两种创作在动手之前都先让模型自己判断"信息够不够/说不说得通"：
    needs_clarification（缺关键信息，追问一次——见 play_turn.py 的
    PendingClarification 挂起态）、reject（说不通，直接拒绝）、ready（可以创作/
    已确认是已有内容）三态，不是"要么瞎编、要么听不懂"两态。
  - 地点创作额外带一个 list_locations 工具（真正的 function calling，见
    model/services/llm_tool_loop.py）：模型先查一遍游戏里真实存在的地点，
    发现玩家说的其实是已有地点的另一种措辞时直接复用，不新建近似重复的地点。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Callable, Literal, Protocol

from model.services.llm_tool_loop import run_tool_loop
from model.services.result_pool_safety import FIELD_HINT as _FIELD_HINT
from model.services.result_pool_safety import sanitize_result_pool

_logger = logging.getLogger("eventhorizon.live_content_author")

# 事件触发要有结果，不能"发生了"却什么都没变——prompt 已经明确要求 result_pool
# 至少给 1 条，但实测这个模型（glm-4-flash）经常直接不给，哪怕叙事文案写得很
# 完整（三次连续试验，"帮老太太挑水""弹一曲高山流水""帮摊主吆喝""给乞丐钱"
# "练拳法"全部没带 result_pool）。跟拒绝整个事件相比，给一个不痛不痒但方向
# 稳妥的默认效果更实用——总不能因为模型漏填一个字段，就把一句写得好好的叙事
# 整个扔掉，逼玩家重说一遍。用"修为略有精进"：小幅正面、跟叙事内容无关也不
# 违和，比乱猜"该加钱还是扣钱"安全。
_DEFAULT_RESULT_POOL = [{"kind": "state_change", "field": "cultivation", "delta": 1.0}]


class LlmClient(Protocol):
    def complete(self, prompt: str) -> str: ...
    def complete_with_tools(self, messages: list[dict], tools: list[dict]) -> dict: ...


_COMMAND_PROMPT_TEMPLATE = (
    "你是一款文字修仙游戏的实时叙事引擎。玩家当前身处「{location_type}」，说：\n"
    "「{player_text}」\n\n"
    "只输出下面三种情况之一对应的 JSON，不要有任何多余文字、解释或代码块标记"
    "（不要用 ```）：\n\n"
    "1. 这句话缺了关键信息，没法确定具体该发生什么场景（比如说了动作但看不出"
    "对象/方式，含糊到没法落笔）：只输出\n"
    '{{"needs_clarification": true, "question": "一句自然的追问，帮玩家把话说清楚"}}\n\n'
    "2. 这句话明显不构成任何合理的游戏内动作（乱敲的字符、跟修仙世界毫无关系的话、"
    "纯粹的测试文本）：只输出\n"
    '{{"reject": true}}\n\n'
    "3. 这句话确实表达了一个具体、能直接构思出场景的动作意图（即使措辞不寻常）："
    "构思一个刚好能回应这个动作的场景，只输出一个 JSON 数组，恰好 1 个元素，"
    "形如：\n"
    '[{{"tags": ["生活"], "aliases": [], "variants": ["第二人称叙事文案，'
    '40-120字，古风白话文风格"], "weight": 1.0, "duration_shichen": 1, '
    '"cooldown_shichen": 0, "priority": 5, "result_pool": [], "item_query": ""}}]\n'
    "（这一支适用：tags 从「生活、修炼、社交、奇遇、战斗、经济」里选 1-2 个；"
    "result_pool 至少给 1 条、最多 3 条，不能给空数组——玩家做了这个动作，就该有"
    "点什么随之变化，哪怕很小（帮了别人得点感激/小赏钱，出了力饱食略降，动了气"
    "心魔略升，破财或得财，诸如此类），不能让「发生了」和「什么都没变」划等号；"
    "只能是 state_change，field 只能从这几个里选：" + _FIELD_HINT + "；"
    "variants 里只能用这些占位符：{{地点}} {{境界}} {{金钱}} "
    "{{年龄}} {{天气}} {{对象}}）"
)

_LOCATION_PROMPT_TEMPLATE = (
    "你是一款文字修仙游戏的实时叙事助手。玩家当前身处「{current_name}」"
    "（地点类型：{current_type}），说想去「{hint}」，但按名字/别名直接查找没找到"
    "现成的地点。你可以调用 list_locations 工具查看游戏里当前真实存在的地点，"
    "确认「{hint}」是不是其实就是某个已有地点的另一种说法（措辞不同但明显是同"
    "一个地方），避免创作出一个跟已有地点撞车的近似重复地点。\n\n"
    "确认完之后，只输出一个 JSON 对象，不要有任何多余文字、解释或代码块标记"
    "（不要用 ```），是下面这几种之一：\n"
    '1. 其实是已有地点（只是措辞不同）：{{"existing_location_id": "从 list_locations '
    '结果里选一个 location_id"}}\n'
    '2. 当前地点内部/近旁的一个新子场所（比如城市里的集市、藏经阁、演武场——玩家'
    '在城里逛逛就能到，不构成一次远行）：{{"name": "地点名，2-6个汉字，符合修仙'
    '世界观", "kind": "从这几个类型里选一个：{kinds}", "is_internal": true}}\n'
    '3. 一个明显在外部的新地方（比如另一座城市、门派、地域）：跟 2 同样的字段，'
    '"is_internal": false\n'
    '4. 这句话本身太含糊，判断不出是找已有地点还是要去一个什么样的新地方：'
    '{{"needs_clarification": true, "question": "一句自然的追问"}}\n'
    '5. 完全说不通、纯粹的胡言乱语：{{"reject": true}}'
)


@dataclass(frozen=True, slots=True)
class LiveLocationDecision:
    name: str
    kind: str
    location_type: str
    is_internal: bool


@dataclass(frozen=True, slots=True)
class LiveAuthorOutcome:
    """author_command_event/author_location 共用的三态结果——ready 才是"可以
    真的落库/生效"，needs_clarification 对应 play_turn.py 的 PendingClarification
    挂起态（追问一次，最多 3 轮，见那边的实现），reject 走调用方原有的"听不懂"/
    "找不到地方"兜底文案。"""

    kind: Literal["ready", "needs_clarification", "reject"]
    command_raw: dict | None = None
    location_decision: "LiveLocationDecision | None" = None
    existing_location_id: str | None = None
    question: str | None = None


def _clamp_float(value, default: float, lo: float, hi: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def _clamp_int(value, default: int, lo: int, hi: int) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


class LiveContentAuthor:
    def __init__(self, client: LlmClient) -> None:
        self._client = client

    def author_command_event(self, player_text: str, location_type: str) -> LiveAuthorOutcome:
        prompt = _COMMAND_PROMPT_TEMPLATE.format(player_text=player_text, location_type=location_type)
        try:
            raw = self._client.complete(prompt)
        except Exception as exc:
            _logger.warning("实时事件创作失败：%s", exc)
            return LiveAuthorOutcome(kind="reject")
        parsed = _parse_json_value(raw)
        if isinstance(parsed, dict):
            if parsed.get("needs_clarification"):
                question = str(parsed.get("question") or "").strip()
                if question:
                    return LiveAuthorOutcome(kind="needs_clarification", question=question)
            return LiveAuthorOutcome(kind="reject")
        if not isinstance(parsed, list) or not parsed:
            return LiveAuthorOutcome(kind="reject")
        item = parsed[0]
        if not isinstance(item, dict):
            return LiveAuthorOutcome(kind="reject")
        variants = [str(v).strip() for v in item.get("variants", []) if str(v).strip()]
        if not variants:
            return LiveAuthorOutcome(kind="reject")
        result_pool = sanitize_result_pool(item.get("result_pool"))
        if not result_pool:
            # 模型没给结果——不拒绝（叙事文案往往是完整的，扔掉太浪费），落到
            # 模块顶部的 _DEFAULT_RESULT_POOL，见那边注释。
            _logger.warning("实时创作的事件缺少 result_pool，落到默认效果：%s", variants[0])
            result_pool = list(_DEFAULT_RESULT_POOL)
        command_raw = {
            "tags": [str(t).strip() for t in item.get("tags", []) if str(t).strip()],
            "aliases": [str(a).strip() for a in item.get("aliases", []) if str(a).strip()],
            "variants": variants,
            "weight": _clamp_float(item.get("weight"), default=1.0, lo=0.1, hi=5.0),
            "duration_shichen": _clamp_int(item.get("duration_shichen"), default=1, lo=0, hi=8),
            "cooldown_shichen": _clamp_int(item.get("cooldown_shichen"), default=0, lo=0, hi=48),
            "priority": _clamp_int(item.get("priority"), default=5, lo=1, hi=9),
            "result_pool": result_pool,
        }
        return LiveAuthorOutcome(kind="ready", command_raw=command_raw)

    def author_location(
        self, hint: str, current_location_name: str, current_location_type: str,
        list_locations: "Callable[[], list[dict]]",
    ) -> LiveAuthorOutcome:
        from model.domain.map import LocationKind

        kinds = [k.value for k in LocationKind]
        prompt = _LOCATION_PROMPT_TEMPLATE.format(
            current_name=current_location_name, current_type=current_location_type, hint=hint, kinds="、".join(kinds)
        )
        tools = [{
            "type": "function",
            "function": {
                "name": "list_locations",
                "description": "查询游戏里当前真实存在、玩家可见的地点列表",
                "parameters": {"type": "object", "properties": {}},
            },
        }]
        tool_impls = {"list_locations": lambda: list_locations()}
        content = run_tool_loop(self._client, [{"role": "user", "content": prompt}], tools, tool_impls)
        if content is None:
            return LiveAuthorOutcome(kind="reject")
        item = _parse_json_object(content)
        if item is None:
            return LiveAuthorOutcome(kind="reject")
        if item.get("reject"):
            return LiveAuthorOutcome(kind="reject")
        if item.get("needs_clarification"):
            question = str(item.get("question") or "").strip()
            if question:
                return LiveAuthorOutcome(kind="needs_clarification", question=question)
            return LiveAuthorOutcome(kind="reject")
        existing_id = item.get("existing_location_id")
        if existing_id:
            return LiveAuthorOutcome(kind="ready", existing_location_id=str(existing_id))
        name = str(item.get("name", "")).strip()
        kind = str(item.get("kind", "")).strip()
        if not name or kind not in kinds:
            return LiveAuthorOutcome(kind="reject")
        decision = LiveLocationDecision(
            name=name, kind=kind, location_type=kind, is_internal=bool(item.get("is_internal", False))
        )
        return LiveAuthorOutcome(kind="ready", location_decision=decision)


def _parse_json_value(raw: str):
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        _logger.warning("LLM output is not valid JSON, discarding")
        return None


def _parse_json_object(raw: str) -> dict | None:
    parsed = _parse_json_value(raw)
    return parsed if isinstance(parsed, dict) else None
