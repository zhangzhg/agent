"""model/services/pipeline.py — 责任链：产 diff → apply → log（对应 README 3.6）。

固定顺序，插件不能插队到校验之前：Validation → DomainStrategy → ApplyDiff → Log。

rejected 与 stopped 必须分开：前者是"这条事件根本不该发生"（状态原样、无日志），
后者是"算到一半不再往下算，但已发生的照落"。混成一个布尔量会让突破失败这类事件
要么丢掉扣除、要么把谓词失败也记进日志。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from model.domain.diff import AppliedDiff, WorldDiff, apply_agent_diff, apply_world_diff

if TYPE_CHECKING:
    from model.domain.agent import Agent
    from model.domain.events import GameEventDef, GameEventOccurrence
    from model.domain.map import WorldView
    from model.services.ports import EventLogStore


@dataclass
class PipelineContext:
    occurrence: "GameEventOccurrence"
    event_def: "GameEventDef"
    agent: "Agent"  # 只读快照来源；步骤禁止直接赋值它的字段
    world: "WorldView"
    rejected: bool = False  # 校验未过：什么都没发生，不 apply、不写日志
    stopped: bool = False  # 中途终止：已产出的 diff 仍然生效
    diff: AppliedDiff = field(default_factory=AppliedDiff)  # 累加中的 Agent 差分
    world_diff: WorldDiff = field(default_factory=WorldDiff)
    chosen_variant: int = 0
    spawned: list["GameEventOccurrence"] = field(default_factory=list)  # 待 publish 的连锁


class PipelineStep(Protocol):
    def handle(self, ctx: PipelineContext) -> None: ...


class ValidationStep:
    def handle(self, ctx: PipelineContext) -> None:
        if ctx.event_def.predicate and not ctx.event_def.predicate.evaluate(ctx.agent.as_eval_context(ctx.world)):
            ctx.rejected = True


# 不设 ResourceStep：扣钱/食物/时间只在结果池 StateChange / ItemConsume


class DomainStrategyStep:
    """策略只往 ctx.diff 累加，不碰 ctx.agent 的字段。"""

    def __init__(self, handler) -> None:
        self._handler = handler

    def handle(self, ctx: PipelineContext) -> None:
        self._handler.handle(ctx)


class ApplyDiffStep:
    """全链唯一的写入点。跑到这里说明结果池已全部算完、没有抛异常。"""

    def handle(self, ctx: PipelineContext) -> None:
        if ctx.rejected:
            return
        apply_agent_diff(ctx.agent, ctx.diff)
        apply_world_diff(ctx.world.mutable_state(), ctx.world_diff)


class LogStep:
    """把 diff 挂到 Occurrence 上并追加日志（脏标记，不做全量快照）。
    CauseLink 已经在 ctx.diff.causes_add 里，这里不再单独写一遍。"""

    def __init__(self, log: "EventLogStore | None" = None) -> None:
        self._log = log

    def handle(self, ctx: PipelineContext) -> None:
        if ctx.rejected:
            return
        ctx.occurrence.applied_diff = ctx.diff
        ctx.occurrence.world_diff = ctx.world_diff if ctx.world_diff.location_changes else None
        ctx.occurrence.chosen_variant_index = ctx.chosen_variant
        if self._log is not None:
            self._log.append(ctx.occurrence)


class Pipeline:
    """固定顺序，插件不能插队到校验之前（README 3.5 约束）：
    Validation → DomainStrategy → ApplyDiff → Log"""

    def __init__(self, steps: list[PipelineStep]) -> None:
        self._steps = steps

    def run(self, ctx: PipelineContext) -> PipelineContext:
        for step in self._steps:
            if ctx.rejected:
                break  # 校验未过：连 ApplyDiff 都不跑
            if ctx.stopped and not isinstance(step, (ApplyDiffStep, LogStep)):
                continue  # 中途终止仍要落已产出的 diff
            step.handle(ctx)
        return ctx


def default_pipeline(handler, log: "EventLogStore | None" = None) -> Pipeline:
    """标准四步链：Validation → DomainStrategy(handler) → ApplyDiff → Log。"""
    return Pipeline([ValidationStep(), DomainStrategyStep(handler), ApplyDiffStep(), LogStep(log)])
