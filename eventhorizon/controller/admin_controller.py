"""controller/admin_controller.py — 录入编辑器 Web 入口（ARCHITECTURE §1.3.3 /
GAME_DESIGN §9.3）。

薄：地图/物品是直接读写 app_ctx.world / app_ctx.items 的字典型仓库（内容录入，
不是对局状态改动，不走 apply_agent_diff/apply_world_diff 那套 diff 机制——跟
content/seed.py 的预置内容加载走的是同一条路）；事件校验/保存全部委派给
model/services/event_validation.py 的同一份函数（跟 editor_controller.py 用的
函数完全一样，不重写一份），不直调 pipeline / matching / arbiter。
"""
from __future__ import annotations

import random
from dataclasses import replace
from typing import TYPE_CHECKING

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from model.domain.agent import AgentEventHistory
from model.domain.events import GameEventDef
from model.domain.items import ItemDef, ItemKind
from model.domain.map import Location, LocationCondition, LocationKind, Route
from model.services.event_validation import ValidationCatalog, validate_event_def
from model.services.simulation_service import simulate_trigger
from view.schemas.admin_schemas import (
    EventDetailDTO,
    EventSummaryDTO,
    FieldErrorDTO,
    ItemDTO,
    LocationDTO,
    RouteDTO,
    SaveEventResponse,
    SaveLocationResponse,
    SimulateRequest,
    SimulateResponse,
)
from view.web.admin_page import render_admin_page

if TYPE_CHECKING:
    from bootstrap import AppContext


def register_admin_routes(fastapi_app: FastAPI, app_ctx: "AppContext") -> None:
    @fastapi_app.get("/admin", response_class=HTMLResponse)
    def admin_index() -> str:
        return render_admin_page()

    # ---------- 地图 / 城市 ----------

    @fastapi_app.get("/api/admin/locations", response_model=list[LocationDTO])
    def list_locations() -> list[LocationDTO]:
        return [_location_to_dto(loc) for loc in app_ctx.world.locations.values()]

    @fastapi_app.post("/api/admin/locations", response_model=SaveLocationResponse)
    def save_location(dto: LocationDTO) -> SaveLocationResponse:
        try:
            kind = LocationKind(dto.kind)
            condition = LocationCondition(dto.condition)
        except ValueError as exc:
            return SaveLocationResponse(ok=False, field_errors=[FieldErrorDTO(field="kind/condition", message=str(exc))])
        if dto.parent_location_id and dto.parent_location_id not in app_ctx.world.locations:
            return SaveLocationResponse(
                ok=False, field_errors=[FieldErrorDTO(field="parent_location_id", message="父地点不存在")]
            )
        app_ctx.world.locations[dto.location_id] = Location(
            location_id=dto.location_id,
            name=dto.name,
            kind=kind,
            location_type=dto.location_type,
            x=dto.x,
            y=dto.y,
            qi_density=dto.qi_density,
            danger_level=dto.danger_level,
            condition=condition,
            parent_location_id=dto.parent_location_id or None,
            hidden=dto.hidden,
            concealment=dto.concealment,
            discovered=dto.discovered,
        )
        app_ctx.world_repo.save(app_ctx.clock.now())
        return SaveLocationResponse(ok=True)

    @fastapi_app.delete("/api/admin/locations/{location_id}", response_model=SaveLocationResponse)
    def delete_location(location_id: str) -> SaveLocationResponse:
        if location_id not in app_ctx.world.locations:
            raise HTTPException(404, "地点不存在")
        del app_ctx.world.locations[location_id]
        app_ctx.world.routes = [r for r in app_ctx.world.routes if location_id not in (r.from_id, r.to_id)]
        app_ctx.world_repo.save(app_ctx.clock.now())
        return SaveLocationResponse(ok=True)

    @fastapi_app.get("/api/admin/routes", response_model=list[RouteDTO])
    def list_routes() -> list[RouteDTO]:
        return [
            RouteDTO(from_id=r.from_id, to_id=r.to_id, move_cost_shichen=r.move_cost_shichen, bidirectional=r.bidirectional)
            for r in app_ctx.world.routes
        ]

    @fastapi_app.post("/api/admin/routes", response_model=SaveLocationResponse)
    def save_route(dto: RouteDTO) -> SaveLocationResponse:
        errors = []
        if dto.from_id not in app_ctx.world.locations:
            errors.append(FieldErrorDTO(field="from_id", message="地点不存在"))
        if dto.to_id not in app_ctx.world.locations:
            errors.append(FieldErrorDTO(field="to_id", message="地点不存在"))
        if errors:
            return SaveLocationResponse(ok=False, field_errors=errors)
        app_ctx.world.routes = [
            r for r in app_ctx.world.routes if not (r.from_id == dto.from_id and r.to_id == dto.to_id)
        ]
        app_ctx.world.routes.append(
            Route(from_id=dto.from_id, to_id=dto.to_id, move_cost_shichen=dto.move_cost_shichen, bidirectional=dto.bidirectional)
        )
        app_ctx.world_repo.save(app_ctx.clock.now())
        return SaveLocationResponse(ok=True)

    @fastapi_app.delete("/api/admin/routes", response_model=SaveLocationResponse)
    def delete_route(from_id: str, to_id: str) -> SaveLocationResponse:
        before = len(app_ctx.world.routes)
        app_ctx.world.routes = [
            r for r in app_ctx.world.routes if not (r.from_id == from_id and r.to_id == to_id)
        ]
        if len(app_ctx.world.routes) == before:
            raise HTTPException(404, "路线不存在")
        app_ctx.world_repo.save(app_ctx.clock.now())
        return SaveLocationResponse(ok=True)

    # ---------- 物品 ----------

    @fastapi_app.get("/api/admin/items", response_model=list[ItemDTO])
    def list_items() -> list[ItemDTO]:
        return [_item_to_dto(item) for item in app_ctx.items.list_all()]

    @fastapi_app.post("/api/admin/items", response_model=SaveLocationResponse)
    def save_item(dto: ItemDTO) -> SaveLocationResponse:
        try:
            kind = ItemKind(dto.kind)
        except ValueError as exc:
            return SaveLocationResponse(ok=False, field_errors=[FieldErrorDTO(field="kind", message=str(exc))])
        app_ctx.items.save_item_def(
            ItemDef(
                item_id=dto.item_id, kind=kind, stackable=dto.stackable, unique=dto.unique,
                name=dto.name, description=dto.description,
            )
        )
        return SaveLocationResponse(ok=True)

    @fastapi_app.delete("/api/admin/items/{item_id}", response_model=SaveLocationResponse)
    def delete_item(item_id: str) -> SaveLocationResponse:
        if not app_ctx.items.delete_item_def(item_id):
            raise HTTPException(404, "物品不存在")
        return SaveLocationResponse(ok=True)

    # ---------- 事件 ----------

    @fastapi_app.get("/api/admin/events", response_model=list[EventSummaryDTO])
    def list_events() -> list[EventSummaryDTO]:
        return [
            EventSummaryDTO(
                event_id=e.event_id, tags=list(e.tags), applicable_locations=list(e.applicable_locations),
                is_command=e.is_command, is_draft=e.is_draft, weight=e.weight,
            )
            for e in app_ctx.events.list_all()
        ]

    @fastapi_app.get("/api/admin/events/{event_id}", response_model=EventDetailDTO)
    def get_event(event_id: str) -> EventDetailDTO:
        defn = app_ctx.events.get_by_id(event_id)
        if defn is None:
            raise HTTPException(404, "事件不存在")
        return _event_to_dto(defn)

    @fastapi_app.post("/api/admin/events", response_model=SaveEventResponse)
    def save_event(dto: EventDetailDTO) -> SaveEventResponse:
        raw = dto.model_dump()
        catalog = _build_catalog(app_ctx)
        defn, errors = validate_event_def(raw, catalog)
        if defn is None:
            return SaveEventResponse(ok=False, field_errors=[FieldErrorDTO(field=e.field, message=e.message) for e in errors])
        app_ctx.events.save_event_def(defn)
        _refresh_parser_if_needed(app_ctx)
        return SaveEventResponse(ok=True, event_id=defn.event_id)

    @fastapi_app.post("/api/admin/events/{event_id}/publish", response_model=SaveEventResponse)
    def publish_event(event_id: str) -> SaveEventResponse:
        defn = app_ctx.events.get_by_id(event_id)
        if defn is None:
            raise HTTPException(404, "事件不存在")
        app_ctx.events.save_event_def(replace(defn, is_draft=False))
        _refresh_parser_if_needed(app_ctx)
        return SaveEventResponse(ok=True, event_id=event_id)

    @fastapi_app.post("/api/admin/events/{event_id}/unpublish", response_model=SaveEventResponse)
    def unpublish_event(event_id: str) -> SaveEventResponse:
        """撤回发布，退回草稿态——不进 1.4.2 粗筛合格池，方便改错内容后再发布。"""
        defn = app_ctx.events.get_by_id(event_id)
        if defn is None:
            raise HTTPException(404, "事件不存在")
        app_ctx.events.save_event_def(replace(defn, is_draft=True))
        _refresh_parser_if_needed(app_ctx)
        return SaveEventResponse(ok=True, event_id=event_id)

    @fastapi_app.delete("/api/admin/events/{event_id}", response_model=SaveEventResponse)
    def delete_event(event_id: str) -> SaveEventResponse:
        if not app_ctx.events.delete_event_def(event_id):
            raise HTTPException(404, "事件不存在")
        _refresh_parser_if_needed(app_ctx)
        return SaveEventResponse(ok=True, event_id=event_id)

    # ---------- 模拟触发沙盒（ARCHITECTURE §1.3.3）----------

    @fastapi_app.post("/api/admin/simulate", response_model=SimulateResponse)
    def simulate(request: SimulateRequest) -> SimulateResponse:
        outcome = simulate_trigger(
            app_ctx.events, request.event_id, request.context_snapshot,
            AgentEventHistory(), request.sample_n, random.Random(),
        )
        return SimulateResponse(
            passed_coarse_filter=outcome.passed_coarse_filter,
            relative_weight_share=outcome.relative_weight_share,
            hit_distribution=outcome.hit_distribution,
        )


def _refresh_parser_if_needed(app_ctx: "AppContext") -> None:
    from bootstrap import refresh_chat_parser

    refresh_chat_parser(app_ctx)


def _build_catalog(app_ctx: "AppContext") -> ValidationCatalog:
    return ValidationCatalog(
        known_item_ids={i.item_id for i in app_ctx.items.list_all()},
        known_event_ids={e.event_id for e in app_ctx.events.list_all()},
        known_scenario_ids=set(app_ctx.scenarios.graphs.keys()),
    )


def _location_to_dto(loc: Location) -> LocationDTO:
    return LocationDTO(
        location_id=loc.location_id, name=loc.name, kind=loc.kind.value, location_type=loc.location_type,
        x=loc.x, y=loc.y, qi_density=loc.qi_density, danger_level=loc.danger_level, condition=loc.condition.value,
        parent_location_id=loc.parent_location_id, hidden=loc.hidden, concealment=loc.concealment,
        discovered=loc.discovered,
    )


def _item_to_dto(item: ItemDef) -> ItemDTO:
    return ItemDTO(
        item_id=item.item_id, kind=item.kind.value, name=item.name, description=item.description,
        stackable=item.stackable, unique=item.unique,
    )


def _event_to_dto(defn: GameEventDef) -> EventDetailDTO:
    from model.repositories.codec import predicate_to_dict, result_to_dict

    return EventDetailDTO(
        event_id=defn.event_id,
        applicable_locations=list(defn.applicable_locations),
        applicable_time=list(defn.applicable_time) if defn.applicable_time is not None else None,
        predicate=predicate_to_dict(defn.predicate) if defn.predicate is not None else None,
        weight=defn.weight,
        duration_shichen=defn.duration_shichen,
        cooldown_shichen=defn.cooldown_shichen,
        max_trigger_per_agent=defn.max_trigger_per_agent,
        exclusive_tags=list(defn.exclusive_tags),
        priority=defn.priority,
        tags=list(defn.tags),
        aliases=list(defn.aliases),
        result_pool=[result_to_dict(r) for r in defn.result_pool],
        variants=[{"text": v.text, "weight": v.weight} for v in defn.variants],
        reply_options=[
            {
                "aliases": list(ro.aliases),
                "results": [result_to_dict(r) for r in ro.results],
                "chain_event_id": ro.chain_event_id,
                "response_text": ro.response_text,
            }
            for ro in defn.reply_options
        ],
        novelty_curve_override=defn.novelty_curve_override,
        scenario_ref=defn.scenario_ref,
        is_draft=defn.is_draft,
        is_command=defn.is_command,
    )
