"""model/domain/results.py — 类型化结果池（禁止 payload: dict，对应 README 1.3.2）。

扣饭钱、加饱食、移动地点只走 StateChange / ItemConsume，责任链不再另设"扣资源"步。
ResultPoolExecutor 把每条 Result 翻译成 AppliedDiff 片段并累加，自己不碰 Agent。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union

from model.domain.events import TriggerSource


@dataclass(frozen=True, slots=True)
class ItemDrop:
    item_id: str
    n: int = 1


@dataclass(frozen=True, slots=True)
class ItemConsume:
    item_id: str
    n: int = 1


@dataclass(frozen=True, slots=True)
class StateChange:
    field: str  # satiety | money | cultivation | heart_demon | location
    delta: int | float | None = None
    set_to: str | int | None = None


@dataclass(frozen=True, slots=True)
class Check:
    kind: str  # breakthrough | combat
    # 系数不写在这里：执行时按 kind 从 BalanceTable 读公式参数（§3.5）
    on_success: tuple["Result", ...] = field(default_factory=tuple)
    on_fail: tuple["Result", ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class WriteCause:
    tag: str
    target: str
    expires_years: int | None = None


@dataclass(frozen=True, slots=True)
class ChainEvent:
    event_id: str
    source_override: TriggerSource = TriggerSource.CHAIN


@dataclass(frozen=True, slots=True)
class StartScenario:
    scenario_id: str


@dataclass(frozen=True, slots=True)
class FlagSet:
    """置位一个 flag（如"已拜师""遭遇战斗"）。AppliedDiff 早就有 flags_set 字段，
    但原设计漏了一个 Result 类型去产出它——没有这个，内容作者压根写不出"设标志"
    这条结果，FLAG 谓词也就无从被任何结果池点亮。"""

    name: str


@dataclass(frozen=True, slots=True)
class FlagClear:
    name: str


Result = Union[
    ItemDrop, ItemConsume, StateChange, Check, WriteCause, ChainEvent, StartScenario, FlagSet, FlagClear
]
