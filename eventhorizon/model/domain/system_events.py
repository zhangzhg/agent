"""model/domain/system_events.py — 系统级总线事件（对应 README 3.2 / 3.4）。

TimePassEvent / MapUpdateEvent / DeathEvent / AgentStateChanged 各用一个工厂 +
Handler 注册进 EventRegistry（`type` 键）；库内一般事件（eat/meditate/…）走
GameEventOccurrence，用 event_id 键，两套键互不混用（README 3.4）。
"""
from __future__ import annotations

from dataclasses import dataclass

from model.domain.diff import LocationAttrChange
from model.domain.time import GameTime


@dataclass(frozen=True, slots=True)
class TimePassEvent:
    """时辰更替 / 日出日落 / 月圆之夜等周期性时间事件（README 1.2.1）。"""

    at: GameTime
    crossed_day: bool = False


@dataclass(frozen=True, slots=True)
class MapUpdateEvent:
    """节点状态剧变（如大战发生），触发地图拓扑或属性变更（README 1.2.2）。"""

    location_id: str
    changes: tuple[LocationAttrChange, ...]


@dataclass(frozen=True, slots=True)
class DeathEvent:
    """寿元归零、天劫失败、走火入魔未救治时发布（README 2.5）。"""

    agent_id: str
    at: GameTime
    cause: str  # "寿元耗尽" | "天劫" | "走火入魔" | ...


@dataclass(frozen=True, slots=True)
class AgentStateChanged:
    """状态切换成功后由 PlayTurnService publish，供 UI 和日程订阅（README 3.3）。"""

    agent_id: str
    new_state_name: str
