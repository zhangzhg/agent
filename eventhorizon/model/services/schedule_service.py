"""model/services/schedule_service.py — 日程：提高标签权重（对应 README 1.5.2 /
4.13，V1）。

NPC（及主角可选）在特定时辰自动从事件库里触发生活事件。Schedule 把某时辰的权重
偏向某一标签，不保证该时辰必触发该事件；空闲且时辰命中时，将该标签并入本轮合格
池再加权随机，以 TriggerSource=schedule 走 execute_occurrence，与玩家侧同一条路径。
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

from model.domain.events import TriggerSource
from model.services.matching import MatchContext, coarse_filter, reweight_and_pick

if TYPE_CHECKING:
    from model.domain.agent import Agent
    from model.domain.events import GameEventDef
    from model.domain.time import GameTime
    from model.services.ports import EventRepository


@dataclass
class ScheduleEntry:
    shichen: tuple[int, ...]
    boosted_tag: str
    weight_multiplier: float = 3.0


@dataclass
class Schedule:
    entries: list[ScheduleEntry] = field(default_factory=list)

    def boosted_tag_at(self, shichen: int) -> tuple[str, float] | None:
        for entry in self.entries:
            if shichen in entry.shichen:
                return entry.boosted_tag, entry.weight_multiplier
        return None


class ScheduleService:
    """空闲且时辰命中时，将标签并入合格池再加权随机；抽不中即本轮无事。"""

    def __init__(
        self,
        events: "EventRepository",
        rng: random.Random | None = None,
        schedules: dict[str, Schedule] | None = None,
        executor: "Callable[[Agent, GameEventDef, TriggerSource], None] | None" = None,
    ) -> None:
        self._events = events
        self._rng = rng or random.Random()
        self._schedules = schedules or {}
        self._executor = executor  # 通常绑定 PlayTurnService.execute_occurrence

    def maybe_trigger(self, agent: "Agent", now: "GameTime") -> None:
        if agent.state.name != "idle":
            return  # 只在空闲时触发，行动中/挂起态由仲裁器丢弃日程投递
        schedule = self._schedules.get(agent.agent_id)
        boost = schedule.boosted_tag_at(now.shichen) if schedule else None

        pool = [e for e in self._events.load_event_defs(agent.location_type) if not e.is_command]
        mctx = MatchContext(
            location=agent.location_id,
            location_type=agent.location_type,
            time_shichen=now.shichen,
            now=now,
            age=agent.age,
            realm=agent.realm,
            money=agent.money,
            causes=agent.causes,
        )
        candidates = coarse_filter(pool, mctx, agent.as_eval_context(), agent.event_history)
        if boost is not None:
            tag, multiplier = boost
            candidates = _apply_tag_boost(candidates, tag, multiplier)
        picked = reweight_and_pick(candidates, agent.event_history, self._rng)
        if picked is None or self._executor is None:
            return
        self._executor(agent, picked, TriggerSource.SCHEDULE)


def _apply_tag_boost(candidates: list["GameEventDef"], tag: str, multiplier: float) -> list["GameEventDef"]:
    """把命中标签的候选临时"复制加权"——不改 GameEventDef 本身（不可变），
    用重复放入候选表模拟权重提升，交给同一个 reweight_and_pick 处理。"""
    boosted = list(candidates)
    for c in candidates:
        if tag in c.tags:
            boosted.extend([c] * max(0, int(multiplier) - 1))
    return boosted
