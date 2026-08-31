"""controller/editor_controller.py — 编辑器薄入口（对应 README §7 / 1.3.3 /
1.3.4）。

只编排保存定义、LlmEventAuthor、模拟触发沙盒；校验逻辑委派给
model/services/event_validation.py，模拟沙盒委派给
model/services/simulation_service.py——两处都复用运行时同一份定义，不在
controller 里重写一次（README 1.3.3："校验规则与运行时复用同一套定义，避免
编辑器与运行时两套标准"）。controller/** 不直调 pipeline / matching / arbiter
（README §9 架构守卫测试），故这里不 import model.services.matching。
"""
from __future__ import annotations

import random
from dataclasses import replace
from typing import TYPE_CHECKING

from model.services.event_validation import ValidationCatalog, validate_event_def
from model.services.simulation_service import simulate_trigger
from view.schemas.editor_schemas import (
    GenerateDraftRequest,
    GenerateDraftResponse,
    SaveEventDraftRequest,
    SaveEventDraftResponse,
    SimulateTriggerRequest,
    SimulateTriggerResponse,
)

if TYPE_CHECKING:
    from model.domain.agent import AgentEventHistory
    from model.repositories.llm.llm_event_author import LlmEventAuthor
    from model.services.ports import EventRepository


class EditorController:
    def __init__(
        self,
        events: "EventRepository",
        catalog: ValidationCatalog | None = None,
        llm_author: "LlmEventAuthor | None" = None,
        rng: random.Random | None = None,
    ) -> None:
        self._events = events
        self._catalog = catalog or ValidationCatalog()
        self._llm_author = llm_author
        self._rng = rng or random.Random()

    def save_draft(self, request: SaveEventDraftRequest) -> SaveEventDraftResponse:
        defn, errors = validate_event_def(request.raw_event, self._catalog)
        if defn is None:
            return SaveEventDraftResponse(ok=False, field_errors=[{"field": e.field, "message": e.message} for e in errors])
        self._events.save_event_def(defn)
        return SaveEventDraftResponse(ok=True, event_id=defn.event_id)

    def generate_draft(self, request: GenerateDraftRequest) -> GenerateDraftResponse:
        if self._llm_author is None:
            return GenerateDraftResponse(rejected=[{"error": "LlmEventAuthor 未配置"}])
        drafts = self._llm_author.generate_draft(request.description, request.constraints)
        for defn in drafts:
            self._events.save_event_def(defn)  # 默认草稿，不进合格池；人工点发布才参与对局抽取
        from model.repositories.codec import event_def_to_dict

        return GenerateDraftResponse(drafts=[event_def_to_dict(d) for d in drafts])

    def publish(self, event_id: str) -> bool:
        """人工点发布：把草稿的 is_draft 翻为 False，才进 1.4.2 粗筛的合格池。"""
        defn = self._events.get_by_id(event_id)
        if defn is None:
            return False
        self._events.save_event_def(replace(defn, is_draft=False))
        return True

    def simulate_trigger(
        self, request: SimulateTriggerRequest, history: "AgentEventHistory"
    ) -> SimulateTriggerResponse:
        outcome = simulate_trigger(
            self._events, request.event_id, request.context_snapshot, history, request.sample_n, self._rng
        )
        return SimulateTriggerResponse(
            passed_coarse_filter=outcome.passed_coarse_filter,
            relative_weight_share=outcome.relative_weight_share,
            hit_distribution=outcome.hit_distribution,
        )
