"""model/services/clock_service.py — 时间推进与闭关（对应 README 1.6 / 2.3.1 /
4.11）。

MVP 回合驱动：游戏时间只因事件时长推进，没有墙钟线程。闭关是同步的批量结算循环，
不是后台线程。V1 若接入墙钟循环，只改 GameClock 的驱动方式，advance_for 以下的
结算路径不动。
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

from model.domain.states import ClosedDoorState
from model.domain.time import GameCalendar, GameTime, TimeDilation

if TYPE_CHECKING:
    from model.domain.agent import Agent
    from model.domain.balance import BalanceTable
    from model.domain.map import WorldView
    from model.services.event_bus import EventBus
    from model.services.ports import EventLogStore


class GameClock:
    """全局主时钟：MVP 唯一驱动来源是事件的 duration_shichen（§1 时间模型决策）。"""

    def __init__(self, start: GameTime, bus: "EventBus | None" = None, dilation: TimeDilation | None = None) -> None:
        self._current = start
        self._bus = bus
        self.dilation = dilation or TimeDilation(1.0)

    def now(self) -> GameTime:
        return self._current

    def advance_for(self, agent: "Agent", shichen: int) -> None:
        """推进该 Agent 的时间锚；跨过时辰/日边界时 publish TimePassEvent，
        由 time_pass_handler 刷新天气灵气、并让 schedule_service 挑 NPC 事件。"""
        if shichen <= 0:
            return
        before = self._current
        agent.time_anchor.advance(shichen)
        agent.time_anchor.resync()
        self._current = self._current.add_shichen(shichen)
        crossed_day = (before.day, before.month, before.year) != (
            self._current.day,
            self._current.month,
            self._current.year,
        )
        if self._bus is not None:
            from model.domain.system_events import TimePassEvent

            self._bus.publish(TimePassEvent(at=self._current, crossed_day=crossed_day))


@dataclass
class RetreatBatchResult:
    cultivation_gained: float
    lifespan_spent: float
    shichen_advanced: int
    tidal_days_crossed: int = 0
    interrupted_by_force: bool = False
    force_reason: str | None = None
    stopped_at_target_realm: bool = False


@dataclass
class RetreatSummary:
    """闭关结算摘要（GAME_DESIGN §4.3）：修为/寿元变化 + 期间被跳过的全局事件类型
    汇总，不逐条罗列——呼应 README 1.6"不强制对齐每一件事"。"""

    cultivation_gained: float
    lifespan_spent: float
    shichen_advanced: int
    tidal_days_skipped: int
    interrupted_by_force: bool
    force_reason: str | None
    stopped_at_target_realm: bool
    final_realm: str


def summarize_retreat(results: list[RetreatBatchResult], final_realm: str) -> RetreatSummary:
    return RetreatSummary(
        cultivation_gained=sum(r.cultivation_gained for r in results),
        lifespan_spent=sum(r.lifespan_spent for r in results),
        shichen_advanced=sum(r.shichen_advanced for r in results),
        tidal_days_skipped=sum(r.tidal_days_crossed for r in results),
        interrupted_by_force=bool(results) and results[-1].interrupted_by_force,
        force_reason=results[-1].force_reason if results else None,
        stopped_at_target_realm=bool(results) and results[-1].stopped_at_target_realm,
        final_realm=final_realm,
    )


class RetreatService:
    """闭关 = 局部加速结算（README 1.6），同步批量循环，不是后台线程。"""

    BATCH_SHICHEN = 12  # 每批固定跨度（1 游戏日），对应 §11 TODO#4 的快照频率讨论

    def __init__(
        self, clock: GameClock, balance: "BalanceTable", rng: random.Random | None = None, log: "EventLogStore | None" = None
    ) -> None:
        self._clock = clock
        self._balance = balance
        self._rng = rng or random.Random()
        self._log = log  # 每批结算也要走 apply_agent_diff + 记日志，不能绕过唯一写入点

    def run(
        self,
        agent: "Agent",
        world: "WorldView | None",
        target_shichen: int,
        stop_when: "Callable[[Agent], bool] | None" = None,
    ) -> list[RetreatBatchResult]:
        """target_shichen 始终是安全上限；stop_when(agent) 为 True 时提前结束（用于
        "到金丹为止"这类目标境界式闭关，见 retreat_intent_parser.py）。"""
        from model.domain.diff import AppliedDiff, apply_agent_diff
        from model.domain.events import GameEventOccurrence, TriggerSource

        agent.state = ClosedDoorState()
        results: list[RetreatBatchResult] = []
        remaining = target_shichen
        while remaining > 0:
            batch = min(self.BATCH_SHICHEN, remaining)
            start = self._clock.now()

            qi = world.qi_density_of(agent.location_id) if world is not None else 1.0
            cfg = self._balance.cultivation_rate
            # aptitude 是 GAME_DESIGN §6.1 定义的修炼速度倍率（0.5x~2.0x），原实现漏乘了
            # 它——闭关速度因此对资质完全不敏感，是个真实的 bug，这里补上。
            rate = cfg["base_per_shichen"] * cfg["qi_density_weight"] * qi * agent.aptitude
            self._clock.advance_for(agent, batch)
            end = self._clock.now()

            # 跨越潮汐日按"错过/赶上"结算一次加成，不按天重复刷（README 2.3.1）
            tidal_hits = GameCalendar.tidal_days_crossed(start, end)
            multiplier = cfg["tidal_multiplier"] if tidal_hits > 0 else 1.0
            gained = rate * batch * multiplier
            lifespan_spent = float(batch) / 12.0  # 闭关 100 年 = 寿元 −100（README 2.4），按日折算

            # apply_agent_diff 是全系统唯一改 Agent 的地方（domain/diff.py）；闭关批量
            # 结算不例外，否则读档重放会漏掉这段修为/寿元变化。
            batch_diff = AppliedDiff(attr_deltas=(("cultivation", gained), ("lifespan_left", -lifespan_spent)))
            apply_agent_diff(agent, batch_diff)
            if self._log is not None:
                occ = GameEventOccurrence(
                    event_id="__retreat_batch__",
                    trigger_source=TriggerSource.PLAYER,
                    agent_id=agent.agent_id,
                    occurred_at=end,
                    chosen_variant_index=0,
                    applied_diff=batch_diff,
                )
                self._log.append(occ)

            interrupted, reason = self._maybe_force_event(agent)
            stopped_at_target = stop_when(agent) if stop_when is not None else False
            results.append(
                RetreatBatchResult(
                    cultivation_gained=gained,
                    lifespan_spent=lifespan_spent,
                    shichen_advanced=batch,
                    tidal_days_crossed=tidal_hits,
                    interrupted_by_force=interrupted,
                    force_reason=reason,
                    stopped_at_target_realm=stopped_at_target,
                )
            )
            remaining -= batch
            if interrupted or agent.lifespan_left <= 0 or stopped_at_target:
                break

        # 出关收尾：与普通事件一样一律走 settle()，落点由挂起字段决定（不直接赋 IdleState()）。
        # 抽中 force 中断时，具体的走火入魔/天劫事件由调用方另行以 TriggerSource.FORCE
        # 投递给 PlayTurnService.execute_occurrence 结算，这里只负责跳出批量循环。
        agent.state = agent.state.settle(agent)
        return results

    def _maybe_force_event(self, agent: "Agent") -> tuple[bool, str | None]:
        """抽中 force 事件（走火入魔/天劫/寿元耗尽）立即中断出关。MVP 用固定小概率
        近似"天劫窗口仍随机"（README 2.3.1 §11 TODO#6：窗口只影响粗筛，不做定时器）。"""
        if agent.lifespan_left <= 0:
            return True, "寿元耗尽"
        if self._rng.random() < 0.01:
            return True, "天劫"
        return False, None
