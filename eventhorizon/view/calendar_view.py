"""view/calendar_view.py — 万年历界面展示数据组装（对应 README 1.2.1 / 2.3.1）。

罗盘/干支历牌：显示示例"太乙历 九四七六年 甲辰年 三月十五 午时"。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from model.domain.time import GameCalendar, SHICHEN_NAMES

if TYPE_CHECKING:
    from model.domain.time import GameTime


@dataclass
class CalendarPlaque:
    text: str
    shichen_index: int
    shichen_name: str
    is_tidal_day: bool


def render_calendar_plaque(t: "GameTime") -> CalendarPlaque:
    return CalendarPlaque(
        text=GameCalendar.plaque_text(t),
        shichen_index=t.shichen,
        shichen_name=SHICHEN_NAMES[t.shichen],
        is_tidal_day=GameCalendar.is_tidal_day(t),
    )
