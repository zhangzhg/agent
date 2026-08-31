"""model/services/handlers/result_pool_executor.py — Result 联合类型的唯一分发点
（对应 README 3.2 / 3.3.2，数值公式对应 GAME_DESIGN §7.2 / 7.3）。

把每条 Result 翻译成 diff 片段累加进 ctx.diff / ctx.world_diff，自己不改 Agent。
Check 从 BalanceTable 读系数、用注入的 rng 掷点，再展开对应分支的 Result。
ChainEvent 只往 ctx.spawned 追加 Occurrence，不在本链继续展开。

P(突破) = clamp(资质×灵气浓度×丹药加成 − 心魔 − 境界惩罚, 0.05, 0.95)（GAME_DESIGN §7.2）。
P(胜) = clamp(境界差 + 道具 + 运势 − 心魔, 0.05, 0.95)（GAME_DESIGN §7.3，装备系统未实现，
道具项恒为 0，是已知的范围限制）。修为回退比例与"连续失败触发走火入魔"是跨事件的
计数器行为（Agent.consecutive_breakthrough_failures），content 侧的 on_fail 只管
心魔上升这类可以静态配置的后果，运行时状态相关的部分留在这里。
"""
from __future__ import annotations

import random
from typing import TYPE_CHECKING

from model.domain.balance import BalanceTable, clamp
from model.domain.cause import CauseLink
from model.domain.diff import AppliedDiff, merge
from model.domain.events import GameEventOccurrence, TriggerSource
from model.domain.results import (
    ChainEvent,
    Check,
    FlagClear,
    FlagSet,
    ItemConsume,
    ItemDrop,
    StartScenario,
    StateChange,
    WriteCause,
)
from model.services.scenario_executor import ScenarioExecutor

if TYPE_CHECKING:
    from model.services.pipeline import PipelineContext
    from model.services.ports import ScenarioRepository

SHICHEN_PER_YEAR = 12 * 30 * 12  # 12 时辰/日 * 30 日/月 * 12 月/年（简化历法，见 domain/time.py）
_SET_TO_FIELDS = {"location", "realm"}
NEXT_REALM_SENTINEL = "__next_realm__"  # StateChange(field="realm", set_to=NEXT_REALM_SENTINEL)：
# 突破事件不知道玩家"现在"是哪个境界，只能在执行时动态问 BalanceTable 要下一级


class ResultPoolExecutor:
    def __init__(
        self,
        balance: BalanceTable | None = None,
        rng: random.Random | None = None,
        scenarios: "ScenarioRepository | None" = None,
    ) -> None:
        self._balance = balance or BalanceTable()
        self._rng = rng or random.Random()
        self._scenarios = scenarios
        self._scenario_executor = ScenarioExecutor()

    def execute(self, result, ctx: "PipelineContext") -> None:
        if isinstance(result, ItemDrop):
            ctx.diff = merge(ctx.diff, AppliedDiff(items_add=((result.item_id, result.n),)))
        elif isinstance(result, ItemConsume):
            ctx.diff = merge(ctx.diff, AppliedDiff(items_remove=((result.item_id, result.n),)))
        elif isinstance(result, StateChange):
            ctx.diff = merge(ctx.diff, self._state_change_diff(result, ctx))
        elif isinstance(result, Check):
            self._execute_check(result, ctx)
        elif isinstance(result, WriteCause):
            ctx.diff = merge(ctx.diff, self._write_cause_diff(result, ctx))
        elif isinstance(result, ChainEvent):
            ctx.spawned.append(
                GameEventOccurrence(
                    event_id=result.event_id,
                    trigger_source=result.source_override,
                    agent_id=ctx.agent.agent_id,
                    occurred_at=ctx.occurrence.occurred_at,
                    chosen_variant_index=0,
                )
            )
        elif isinstance(result, StartScenario):
            self._execute_start_scenario(result, ctx)
        elif isinstance(result, FlagSet):
            ctx.diff = merge(ctx.diff, AppliedDiff(flags_set=(result.name,)))
        elif isinstance(result, FlagClear):
            ctx.diff = merge(ctx.diff, AppliedDiff(flags_clear=(result.name,)))
        else:
            raise TypeError(f"unknown Result type: {result!r}")

    def _state_change_diff(self, result: StateChange, ctx: "PipelineContext") -> AppliedDiff:
        if result.field == "scene_focus" and result.set_to is not None:
            # scene_focus 供代词解析回填（ChatParser「它/这个」、GAME_DESIGN §3.1），
            # 一步过期不清空，允许多轮指代。
            return AppliedDiff(scene_focus_set=str(result.set_to))
        if result.field in _SET_TO_FIELDS and result.set_to is not None:
            if result.field == "location":
                new_location_id = str(result.set_to)
                # location_type 必须随 location_id 同步写入，否则 1.4.2 粗筛用的
                # agent.location_type 在移动后就过期了（见 diff.py 的字段注释）。
                location_type = ctx.world.location_type_of(new_location_id) if ctx.world is not None else None
                return AppliedDiff(
                    location_set=new_location_id,
                    location_type_set=location_type or None,
                )
            target_realm = result.set_to
            if target_realm == NEXT_REALM_SENTINEL:
                target_realm = self._balance.next_realm(ctx.agent.realm)
                if target_realm is None:
                    return AppliedDiff()  # 已在最高境界（仙人），突破事件应已被谓词挡住
            return AppliedDiff(realm_set=str(target_realm))
        if result.delta is not None:
            return AppliedDiff(attr_deltas=((result.field, float(result.delta)),))
        return AppliedDiff()

    def _write_cause_diff(self, result: WriteCause, ctx: "PipelineContext") -> AppliedDiff:
        expires_at = None
        if result.expires_years is not None:
            expires_at = ctx.occurrence.occurred_at.add_shichen(result.expires_years * SHICHEN_PER_YEAR)
        cause = CauseLink(
            actor=ctx.agent.agent_id,
            action=ctx.event_def.event_id,
            target=result.target,
            tag=result.tag,
            expires_at=expires_at,
        )
        return AppliedDiff(causes_add=(cause,))

    def _execute_check(self, result: Check, ctx: "PipelineContext") -> None:
        probability = self._probability_for(result.kind, ctx)
        succeeded = self._rng.random() < probability
        if result.kind == "breakthrough":
            ctx.diff = merge(ctx.diff, self._breakthrough_counter_diff(succeeded, ctx))
            if not succeeded and self._crosses_qi_deviation_threshold(ctx):
                self._spawn_qi_deviation(ctx)
        branch = result.on_success if succeeded else result.on_fail
        for sub_result in branch:
            self.execute(sub_result, ctx)

    def _probability_for(self, kind: str, ctx: "PipelineContext") -> float:
        if kind == "breakthrough":
            return self._breakthrough_probability(ctx)
        if kind == "combat":
            return self._combat_probability(ctx)
        return 0.5

    def _breakthrough_probability(self, ctx: "PipelineContext") -> float:
        """GAME_DESIGN §7.2：P = clamp(资质×灵气浓度×丹药加成 − 心魔 − 境界惩罚, 0.05, 0.95)。"""
        cfg = self._balance.breakthrough
        qi = ctx.world.qi_density_of(ctx.agent.location_id) if ctx.world is not None else 1.0
        realm_order = self._balance.realm_order
        realm_rank = realm_order.index(ctx.agent.realm) if ctx.agent.realm in realm_order else 0
        pill_bonus = cfg["pill_bonus_baseline"]  # 丹药 buff 系统留待 V1+，暂恒为基线值
        score = ctx.agent.aptitude * qi * pill_bonus - ctx.agent.heart_demon - cfg["realm_penalty_weight"] * realm_rank
        return clamp(score, cfg["clamp_min"], cfg["clamp_max"])

    def _combat_probability(self, ctx: "PipelineContext", opponent_realm_rank: int | None = None) -> float:
        """GAME_DESIGN §7.3：P(胜) = clamp(境界差 + 道具 + 运势 − 心魔, 0.05, 0.95)。
        opponent_realm_rank 未提供时按同境界处理（无装备/对手建模，已知范围限制）。"""
        cfg = self._balance.combat
        realm_order = self._balance.realm_order
        self_rank = realm_order.index(ctx.agent.realm) if ctx.agent.realm in realm_order else 0
        opp_rank = opponent_realm_rank if opponent_realm_rank is not None else self_rank
        realm_gap_bonus = cfg["realm_gap_weight"] * (self_rank - opp_rank)
        score = realm_gap_bonus + cfg["gear_bonus"] + ctx.agent.luck * cfg["luck_scale"] - ctx.agent.heart_demon
        return clamp(score, cfg["clamp_min"], cfg["clamp_max"])

    def _breakthrough_counter_diff(self, succeeded: bool, ctx: "PipelineContext") -> AppliedDiff:
        """连续失败计数：成功清零，失败 +1、并按比例回退修为（§7.2）。心魔上升留给
        content 的 on_fail 静态配置（如 StateChange(field="heart_demon", delta=0.05)）。"""
        if succeeded:
            if ctx.agent.consecutive_breakthrough_failures == 0:
                return AppliedDiff()
            return AppliedDiff(attr_deltas=(("consecutive_breakthrough_failures", -float(ctx.agent.consecutive_breakthrough_failures)),))
        cfg = self._balance.breakthrough
        setback = ctx.agent.cultivation * cfg["fail_setback_ratio"]
        return AppliedDiff(
            attr_deltas=(("cultivation", -setback), ("consecutive_breakthrough_failures", 1.0))
        )

    def _crosses_qi_deviation_threshold(self, ctx: "PipelineContext") -> bool:
        threshold = self._balance.breakthrough.get("consecutive_fail_threshold", 3)
        return (ctx.agent.consecutive_breakthrough_failures + 1) >= threshold

    def _spawn_qi_deviation(self, ctx: "PipelineContext") -> None:
        """极端失败 chain 走火入魔（README 1.3.2 / GAME_DESIGN §7.2）：force 级，
        event_id 由 BalanceTable 配置，默认约定 "qi_deviation"（content 侧需定义同名事件）。"""
        event_id = self._balance.breakthrough.get("qi_deviation_event_id", "qi_deviation")
        ctx.spawned.append(
            GameEventOccurrence(
                event_id=event_id,
                trigger_source=TriggerSource.FORCE,
                agent_id=ctx.agent.agent_id,
                occurred_at=ctx.occurrence.occurred_at,
                chosen_variant_index=0,
            )
        )

    def _execute_start_scenario(self, result: StartScenario, ctx: "PipelineContext") -> None:
        if self._scenarios is None:
            return
        graph = self._scenarios.get(result.scenario_id)
        if graph is None:
            return
        _node, pending = self._scenario_executor.start(graph, ctx.event_def.event_id)
        ctx.diff = merge(ctx.diff, AppliedDiff(pending_scenario_set=pending))
