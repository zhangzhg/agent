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

安全边界（不是"完全不设防"，而是"不做人工审核，但仍然过自动校验"）：
  - 事件创作直接复用 LlmEventFlavorAuthor（同一套 result_pool 安全过滤：只剩
    state_change，没有 item_drop/chain_event 这类会悬空引用的类型），产出仍然
    要过 validate_event_def() 的联动校验才落库。
  - 地点创作的 kind 必须落在 LocationKind 白名单内，不在白名单直接判失败，不猜、
    不兜底成一个随意值。
  - 模型判断"这句话在情节上说不通"时应该直接拒绝（返回 None），调用方保留原有
    "听不懂"/"找不到地方"文案，不会为了凑数硬编内容。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Protocol

_logger = logging.getLogger("eventhorizon.live_content_author")


class LlmClient(Protocol):
    def complete(self, prompt: str) -> str: ...


_LOCATION_PROMPT_TEMPLATE = (
    "你是一款文字修仙游戏的实时叙事助手。玩家当前身处「{current_name}」"
    "（地点类型：{current_type}），说想去「{hint}」，但游戏里还没有这个地方。\n\n"
    "请判断「{hint}」应该是：\n"
    "1. 当前地点内部/近旁的一个子场所（比如城市里的集市、藏经阁、演武场——玩家"
    "在城里逛逛就能到，不构成一次远行）；\n"
    "2. 一个明显在外部的地方（比如另一座城市、门派、地域——不是靠在城里走两步"
    "就能到的）；\n"
    "3. 完全说不通、纯粹的胡言乱语（比如乱打的字符，或者跟地点毫无关系的话）。\n\n"
    "只输出一个 JSON 对象，不要有任何多余文字、解释或代码块标记（不要用 ```）。\n"
    "如果是 1 或 2，输出形如：\n"
    '{{"name": "地点名，2-6个汉字，符合修仙世界观", "kind": "从这几个类型里选一个：'
    '{kinds}", "is_internal": true 或 false}}\n'
    '如果是 3，输出：{{"reject": true}}'
)


@dataclass(frozen=True, slots=True)
class LiveLocationDecision:
    name: str
    kind: str
    location_type: str
    is_internal: bool


class LiveContentAuthor:
    def __init__(self, client: LlmClient) -> None:
        self._client = client

    def author_command_event(self, player_text: str, location_type: str) -> dict | None:
        """复用 LlmEventFlavorAuthor（跟 admin 编辑器"AI 生成事件"同一套 prompt/
        result_pool 安全过滤），把玩家这句话当"情节描述"喂给它，只要 1 条。返回
        的 dict 形状跟 generate_event_flavors() 单条元素一致；生成失败/模型没给出
        任何可用 variants 都返回 None（不硬凑）。"""
        from model.repositories.llm.llm_event_flavor_author import LlmEventFlavorAuthor

        description = f"玩家在「{location_type}」说：「{player_text}」。请构思一个刚好能回应这句话的场景。"
        try:
            flavors = LlmEventFlavorAuthor(self._client).generate_event_flavors(description, count=1)
        except Exception as exc:
            _logger.warning("实时事件创作失败：%s", exc)
            return None
        return flavors[0] if flavors else None

    def author_location(self, hint: str, current_location_name: str, current_location_type: str) -> LiveLocationDecision | None:
        from model.domain.map import LocationKind

        kinds = [k.value for k in LocationKind]
        prompt = _LOCATION_PROMPT_TEMPLATE.format(
            current_name=current_location_name, current_type=current_location_type, hint=hint, kinds="、".join(kinds)
        )
        try:
            raw = self._client.complete(prompt)
        except Exception as exc:
            _logger.warning("实时地点创作失败：%s", exc)
            return None
        item = _parse_json_object(raw)
        if item is None or item.get("reject"):
            return None
        name = str(item.get("name", "")).strip()
        kind = str(item.get("kind", "")).strip()
        if not name or kind not in kinds:
            return None
        return LiveLocationDecision(
            name=name, kind=kind, location_type=kind, is_internal=bool(item.get("is_internal", False))
        )


def _parse_json_object(raw: str) -> dict | None:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        _logger.warning("LLM output is not valid JSON, discarding")
        return None
    return parsed if isinstance(parsed, dict) else None
