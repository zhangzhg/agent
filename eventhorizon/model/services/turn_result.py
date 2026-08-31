"""model/services/turn_result.py — TurnResult：给 view 的用例产出（对应 README 4.9）。

command_event_id、encounter_event_id、两段 variant_index、两段 AppliedDiff、
parse_error / reject_reason、prompt_event_id（挂起提示）、scenario_node_id。
view 只消费 TurnResult，不依赖 PipelineContext。
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from model.domain.diff import AppliedDiff
    from model.domain.events import GameEventDef
    from model.services.clock_service import RetreatSummary
    from model.services.pipeline import PipelineContext


@dataclass(frozen=True, slots=True)
class TurnResult:
    command_event_id: str | None = None
    command_variant: int = 0
    command_diff: "AppliedDiff | None" = None
    encounter_event_id: str | None = None
    encounter_variant: int = 0
    encounter_diff: "AppliedDiff | None" = None
    prompt_event_id: str | None = None
    prompt_variant: int = 0
    scenario_node_id: str | None = None
    parse_error: str | None = None
    reject_reason: str | None = None
    # 不挂在任何 GameEventDef 变体上的系统文案（如"要闭关多久？"），view 直接透出。
    freeform_narrative: str | None = None
    # 闭关结算摘要是结构化数据，渲染成文案是 view 的活（GAME_DESIGN §4.3）——
    # PlayTurnService 不 import view，只把数据放这里。
    retreat_summary: "RetreatSummary | None" = None
    retreat_before_realm: str | None = None
    retreat_before_cultivation: float | None = None

    @staticmethod
    def parse_failed(message: str) -> "TurnResult":
        return TurnResult(parse_error=message)

    @staticmethod
    def rejected(message: str) -> "TurnResult":
        return TurnResult(reject_reason=message)

    @staticmethod
    def dismissed() -> "TurnResult":
        """挂起项被玩家的下一句无视，按"错过"清空——不是校验拒绝，只是没有叙述可加。"""
        return TurnResult()

    @staticmethod
    def from_one(defn: "GameEventDef", ctx: "PipelineContext") -> "TurnResult":
        return TurnResult(command_event_id=defn.event_id, command_variant=ctx.chosen_variant, command_diff=ctx.diff)

    def with_prompt(self, defn: "GameEventDef", variant: int) -> "TurnResult":
        return replace(self, prompt_event_id=defn.event_id, prompt_variant=variant)

    def plus_encounter(self, defn: "GameEventDef", ctx: "PipelineContext") -> "TurnResult":
        return replace(
            self, encounter_event_id=defn.event_id, encounter_variant=ctx.chosen_variant, encounter_diff=ctx.diff
        )
