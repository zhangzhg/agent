"""model/domain/time.py — 太乙历时间模型（对应 README 1.2.1 / 1.6）。

纯值对象：可比较、可加减，不持有可变状态。可变的"当前时刻"只存在于
model/services/clock_service.py 里的单例 GameClock。GameCalendar 是无状态的
纯函数集合（干支推算、灵气潮汐日判定）。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from functools import total_ordering

SHICHEN_PER_DAY = 12
DAYS_PER_MONTH = 30
MONTHS_PER_YEAR = 12
SHICHEN_NAMES = ("子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥")

_HEAVENLY_STEMS = ("甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸")
_EARTHLY_BRANCHES = SHICHEN_NAMES


class Epoch(str, Enum):
    TAIYI = "太乙历"


def ganzhi_for_year(year: int) -> str:
    """60 一甲子循环推算干支纪年；纪元元年（year=1）记作甲子年。"""
    offset = (year - 1) % 60
    return _HEAVENLY_STEMS[offset % 10] + _EARTHLY_BRANCHES[offset % 12]


@total_ordering
@dataclass(frozen=True, slots=True)
class GameTime:
    """纪元 -> 年(干支) -> 月 -> 日 -> 时辰，可比较、可加减。"""

    epoch: Epoch
    year: int
    ganzhi: str
    month: int
    day: int
    shichen: int  # 0-11

    def _ordinal(self) -> int:
        return (
            ((self.year * MONTHS_PER_YEAR + (self.month - 1)) * DAYS_PER_MONTH + (self.day - 1))
            * SHICHEN_PER_DAY
            + self.shichen
        )

    def __lt__(self, other: "GameTime") -> bool:
        if not isinstance(other, GameTime):
            return NotImplemented
        return self._ordinal() < other._ordinal()

    def add_shichen(self, n: int) -> "GameTime":
        """推进（或倒退）n 个时辰；跨日/月/年自动进位，年变动时重算干支。"""
        total = self._ordinal() + n
        shichen = total % SHICHEN_PER_DAY
        total_days = total // SHICHEN_PER_DAY
        day = total_days % DAYS_PER_MONTH
        total_months = total_days // DAYS_PER_MONTH
        month = total_months % MONTHS_PER_YEAR
        year = total_months // MONTHS_PER_YEAR
        return GameTime(
            epoch=self.epoch,
            year=year,
            ganzhi=ganzhi_for_year(year),
            month=month + 1,
            day=day + 1,
            shichen=shichen,
        )

    def shichen_until(self, other: "GameTime") -> int:
        """other 相对 self 经过的时辰数（可为负），供闭关/离线时长换算。"""
        return other._ordinal() - self._ordinal()

    @staticmethod
    def new(epoch: Epoch, year: int, month: int, day: int, shichen: int) -> "GameTime":
        return GameTime(epoch=epoch, year=year, ganzhi=ganzhi_for_year(year), month=month, day=day, shichen=shichen)


@dataclass(slots=True)
class TimeDilation:
    """游戏时间 : 现实时间，如 60 表示 1 现实秒 = 60 游戏秒。MVP 恒为 1（回合驱动，§1）。"""

    ratio: float = 1.0


@dataclass(slots=True)
class AgentTimeAnchor:
    """1.6 个体时间锚：Agent 当前游戏时间 = last_synced + pending_duration。"""

    last_synced_game_time: GameTime
    pending_duration_shichen: int = 0

    @property
    def current_game_time(self) -> GameTime:
        return self.last_synced_game_time.add_shichen(self.pending_duration_shichen)

    def advance(self, shichen: int) -> None:
        self.pending_duration_shichen += shichen

    def resync(self) -> None:
        """把 pending_duration 并入 last_synced，作为批量结算（闭关）之间的检查点。"""
        self.last_synced_game_time = self.current_game_time
        self.pending_duration_shichen = 0


class GameCalendar:
    """无状态纯函数集合：干支推算、灵气潮汐日判定。不持有可变状态。"""

    TIDAL_DAYS = (1, 15)  # 每月初一、十五：灵气潮汐（README 2.3.1）

    @staticmethod
    def is_tidal_day(t: GameTime) -> bool:
        return t.day in GameCalendar.TIDAL_DAYS

    @staticmethod
    def tidal_days_crossed(start: GameTime, end: GameTime) -> int:
        """区间 (start, end] 内命中的潮汐日次数，供闭关"错过/赶上"只结算一次。"""
        if not start < end:
            return 0
        count = 0
        cursor = GameTime.new(start.epoch, start.year, start.month, start.day, 0)
        while cursor <= end:
            if cursor.day in GameCalendar.TIDAL_DAYS and start < cursor <= end:
                count += 1
            cursor = cursor.add_shichen(SHICHEN_PER_DAY)
        return count

    @staticmethod
    def plaque_text(t: GameTime) -> str:
        """罗盘/干支历牌展示文案，如"太乙历 九四七六年 甲辰年 三月十五 午时"。"""
        return f"{t.epoch.value} {t.year}年 {t.ganzhi}年 {t.month}月{t.day}日 {SHICHEN_NAMES[t.shichen]}时"
