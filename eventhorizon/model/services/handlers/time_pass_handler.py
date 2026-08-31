"""model/services/handlers/time_pass_handler.py — 刷新天气/灵气，检查日程
（对应 README 3.2）。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Iterable

from model.domain.time import GameCalendar

if TYPE_CHECKING:
    from model.domain.agent import Agent
    from model.domain.map import WorldState
    from model.services.schedule_service import ScheduleService
    from model.domain.system_events import TimePassEvent

_WEATHER_CYCLE = ("晴", "阴", "雨", "雾")


class TimePassHandler:
    """订阅 TimePassEvent：刷新天气/灵气；灵气潮汐日提升世界灵气浓度；
    日程是否该 publish 库内事件交给 ScheduleService（可选，V1 接入 NPC 后启用）。"""

    def __init__(
        self,
        world: "WorldState",
        schedule_service: "ScheduleService | None" = None,
        agents_provider: "Callable[[], Iterable[Agent]] | None" = None,
        qi_tide_multiplier: float = 1.5,  # GAME_DESIGN §4.2："全地点灵气浓度 ×1.5"
    ) -> None:
        self._world = world
        self._schedule_service = schedule_service
        self._agents_provider = agents_provider
        self._qi_tide_multiplier = qi_tide_multiplier
        self._base_qi_density: dict[str, float] = {}

    def handle(self, event: "TimePassEvent") -> None:
        self._refresh_weather(event.at)
        self._refresh_qi_tide(event.at)
        if self._schedule_service is not None and self._agents_provider is not None:
            for agent in self._agents_provider():
                self._schedule_service.maybe_trigger(agent, event.at)

    def _refresh_weather(self, at) -> None:
        self._world.weather = _WEATHER_CYCLE[at.shichen % len(_WEATHER_CYCLE)]

    def _refresh_qi_tide(self, at) -> None:
        tide_multiplier = self._qi_tide_multiplier if GameCalendar.is_tidal_day(at) else 1.0
        for location_id, location in self._world.locations.items():
            base = self._base_qi_density.setdefault(location_id, location.qi_density)
            location.qi_density = base * tide_multiplier
