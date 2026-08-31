"""model/domain/events.py — 事件（对应 README 1.3.2 / 1.4.3）。

GameEventDef 与 Occurrence 分离。日志必须带 applied_diff（世界级变更另带
world_diff）：录入日后改结果池，旧档仍按当时差分重放。读档 = 快照 + 逐条 apply
diff，禁止对历史再跑 matching / 责任链。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from model.domain.predicates import PredicateGroup

if TYPE_CHECKING:
    from model.domain.diff import AppliedDiff, WorldDiff
    from model.domain.results import Result
    from model.domain.time import GameTime


class TriggerSource(str, Enum):
    PLAYER = "player"
    SCHEDULE = "schedule"
    ENCOUNTER = "encounter"
    FORCE = "force"
    CHAIN = "chain"


@dataclass(frozen=True, slots=True)
class EventVariant:
    text: str
    weight: float = 1.0


@dataclass(frozen=True, slots=True)
class ReplyOption:
    """跨回合分支：奇遇挂起后，玩家下一句在这张局部表里解析（「买下来」「算了」）。
    非空即表示本条事件 needs_reply——取代原先用 tags 里塞魔法字符串的做法。"""

    aliases: tuple[str, ...]
    results: tuple["Result", ...] = ()
    chain_event_id: str | None = None
    response_text: str = ""  # 这条选项本身的应答文案（如"你付了钱，鱼贩笑呵呵地把
    # 鱼包好递给你"）；宿主事件的 GameEventDef.variants 是"奇遇发生时"的叙述，不是
    # "选了这个选项"的叙述，两者不能共用同一份文案，否则玩家会看到同一句话重复两遍。


@dataclass(frozen=True, slots=True)
class GameEventDef:
    """事件库中的一条定义（录入产物），不可变；运行时不修改它。"""

    event_id: str
    applicable_locations: tuple[str, ...]
    applicable_time: tuple[int, ...] | None
    predicate: PredicateGroup | None
    weight: float
    duration_shichen: int  # README 核心诉求 2「持续时间」：时间推进的唯一来源
    cooldown_shichen: int
    max_trigger_per_agent: int | None
    exclusive_tags: tuple[str, ...]
    priority: int  # 仲裁默认等级，被 TriggerSource 覆盖（README 1.7）
    tags: tuple[str, ...]
    aliases: tuple[str, ...]
    result_pool: tuple["Result", ...]
    variants: tuple[EventVariant, ...]
    reply_options: tuple[ReplyOption, ...] = ()
    novelty_curve_override: dict | None = None
    scenario_ref: str | None = None
    schema_version: int = 1
    is_draft: bool = False
    is_command: bool = False  # True=命令型（eat/move），False=第二段奇遇

    @property
    def needs_reply(self) -> bool:
        return bool(self.reply_options) or self.scenario_ref is not None


@dataclass(slots=True)
class GameEventOccurrence:
    event_id: str
    trigger_source: TriggerSource
    agent_id: str
    occurred_at: "GameTime"
    chosen_variant_index: int
    applied_diff: "AppliedDiff | None" = None
    world_diff: "WorldDiff | None" = None
    def_schema_version: int = 1
