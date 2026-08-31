"""model/services/chat_parser.py — 玩家脑洞文本解析（对应 README 1.11 /
GAME_DESIGN §3.1）。

MVP 是精确别名表（TODO #1：同义词多了会退化成"必须背咒语"，V2 上向量匹配前需要
一版别名覆盖率统计）。只做映射，不调用大模型；失败返回 None。

`move`/`retreat_start`/`inspect_npc` 是"系统命令"（GAME_DESIGN §3.1 表格）：不是
事件库里的 GameEventDef，直接由 ChatParser 内置识别，PlayTurnService / controller
按 event_id 特判处理，不查 EventRepository。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from model.domain.events import GameEventDef
    from model.domain.scenario import ScenarioGraph

MOVE_EVENT_ID = "move"
RETREAT_START_EVENT_ID = "retreat_start"
INSPECT_NPC_EVENT_ID = "inspect_npc"

# 只读查询命令：不改状态、不进 AgentEventHistory，controller 直接调只读服务，不走 PlayTurnService。
QUERY_EVENT_IDS = frozenset({INSPECT_NPC_EVENT_ID})

_MOVE_PREFIXES = ("去", "前往", "回")
_MOVE_PATTERN = re.compile(r"^(?:去|前往|回)\s*(.+)$")
_RETREAT_ALIASES = ("闭关修炼", "闭关")
_INSPECT_PATTERNS = (
    re.compile(r"^打听\s*(.+)$"),
    re.compile(r"^看看那(?:个|位)?人?[，,]?\s*(.*)$"),
)
_PRONOUN_WORDS = ("它", "这个", "那个", "这", "那")
_DEFAULT_OBJECT_FILLABLE_EVENT_IDS = frozenset({"buy", "watch", "fight", "apprentice"})


@dataclass
class ParsedCommand:
    event_id: str
    location_hint: str | None
    target: str | None
    args: dict
    is_query: bool = False  # True：只读查询，controller 不得转给 PlayTurnService


@dataclass
class ParsedReply:
    """挂起态下的解析结果：选中了哪个局部选项 / 哪条流程图出边。"""

    option_index: int | None = None  # 对应 GameEventDef.reply_options
    edge_id: str | None = None  # 对应 ScenarioEdge
    dismissed: bool = False  # 「算了」：放弃挂起项


_DISMISS_PHRASES = ("算了", "不了", "不买了", "走了", "无视", "不管了")


class ChatParser:
    def __init__(
        self,
        alias_to_event_id: dict[str, str],
        object_fillable_event_ids: frozenset[str] = _DEFAULT_OBJECT_FILLABLE_EVENT_IDS,
    ) -> None:
        """短语 → event_id，来自已发布命令型 GameEventDef.aliases（如「吃饭」→ eat）。
        object_fillable_event_ids：这些 event_id 命中「它/这个」等代词时，用
        scene_focus 回填宾语（GAME_DESIGN §3.1 代词解析）。"""
        self._alias_to_event_id = alias_to_event_id
        self._object_fillable_event_ids = object_fillable_event_ids

    def parse(self, raw_text: str, scene_focus: str | None = None) -> ParsedCommand | None:
        """只做映射。失败返回 None（听不懂）。不调用大模型。
        「去围观」在有 scene_focus 时可映射到 watch，target=scene_focus；
        代词解析：「把它买下来」等价于「把{scene_focus}买下来」（§3.1）。"""
        text = raw_text.strip()
        if not text:
            return None

        move_match = self._match_move(text)
        if move_match is not None:
            return move_match

        for pattern in _INSPECT_PATTERNS:
            m = pattern.match(text)
            if m:
                target = m.group(1).strip() or None
                return ParsedCommand(event_id=INSPECT_NPC_EVENT_ID, location_hint=None, target=target, args={}, is_query=True)

        if any(alias in text for alias in _RETREAT_ALIASES):
            return ParsedCommand(event_id=RETREAT_START_EVENT_ID, location_hint=None, target=None, args={})

        for alias, event_id in self._alias_to_event_id.items():
            if alias in text:
                target = self._resolve_target(text, alias, event_id, scene_focus)
                return ParsedCommand(event_id=event_id, location_hint=None, target=target, args={})
        return None

    def _match_move(self, text: str) -> ParsedCommand | None:
        m = _MOVE_PATTERN.match(text)
        if not m:
            return None
        destination = m.group(1).strip()
        if not destination:
            return None
        return ParsedCommand(event_id=MOVE_EVENT_ID, location_hint=destination, target=None, args={})

    def _resolve_target(self, text: str, alias: str, event_id: str, scene_focus: str | None) -> str | None:
        if "围观" in alias or ("看" in alias and event_id != INSPECT_NPC_EVENT_ID):
            return scene_focus
        if event_id in self._object_fillable_event_ids and scene_focus is not None:
            if any(pronoun in text for pronoun in _PRONOUN_WORDS):
                return scene_focus
        return None

    def suggest_aliases(self, candidates: "list[GameEventDef]", n: int = 2) -> list[str]:
        """从当前地点的命令池里现取 n 个常见别名，供软性引导用（GAME_DESIGN §1.1）。
        不是写死的固定文案——PlayTurnService 拿这个拼「要不试试…」。"""
        out: list[str] = []
        for defn in candidates:
            if not defn.is_command or not defn.aliases:
                continue
            out.append(defn.aliases[0])
            if len(out) >= n:
                break
        return out

    def parse_reply(
        self,
        raw_text: str,
        pending: "GameEventDef | None",
        scenario: "ScenarioGraph | None",
        node_id: str | None,
    ) -> ParsedReply | None:
        """挂起态专用：只在局部选项表里匹配（reply_options.aliases 或该节点出边的
        aliases）。与全局别名表分开，「买下来」不必注册成全局命令事件。"""
        text = raw_text.strip()
        if not text:
            return None
        if any(phrase in text for phrase in _DISMISS_PHRASES):
            return ParsedReply(dismissed=True)
        if pending is not None:
            for idx, option in enumerate(pending.reply_options):
                if any(alias in text for alias in option.aliases):
                    return ParsedReply(option_index=idx)
        if scenario is not None and node_id is not None:
            for edge in scenario.edges_from(node_id):
                if any(alias in text for alias in edge.aliases):
                    return ParsedReply(edge_id=edge.edge_id)
        return None
