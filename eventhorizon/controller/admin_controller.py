"""controller/admin_controller.py — 录入编辑器 Web 入口（ARCHITECTURE §1.3.3 /
GAME_DESIGN §9.3）。

薄：地图/物品是直接读写 app_ctx.world / app_ctx.items 的字典型仓库（内容录入，
不是对局状态改动，不走 apply_agent_diff/apply_world_diff 那套 diff 机制——跟
content/seed.py 的预置内容加载走的是同一条路）；事件校验/保存全部委派给
model/services/event_validation.py 的同一份函数（跟 editor_controller.py 用的
函数完全一样，不重写一份），不直调 pipeline / matching / arbiter。
"""
from __future__ import annotations

import logging
import random
import uuid
from dataclasses import replace
from typing import TYPE_CHECKING

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse

from model.domain.agent import AgentEventHistory
from model.domain.events import GameEventDef
from model.domain.items import ItemDef, ItemKind
from model.domain.map import Location, LocationCondition, LocationKind, Route
from model.services.event_validation import ValidationCatalog, validate_event_def
from model.services.local_embedding import embed_with_fallback
from model.services.simulation_service import simulate_trigger
from view.schemas.admin_schemas import (
    EventDetailDTO,
    EventSummaryDTO,
    FieldErrorDTO,
    GenerateEventsRequest,
    GenerateEventsResponse,
    GenerateItemsRequest,
    GenerateItemsResponse,
    GenerateLocationsRequest,
    GenerateLocationsResponse,
    ItemDTO,
    LlmItemItemDTO,
    LlmLocationItemDTO,
    LocationDTO,
    RouteDTO,
    SaveEventResponse,
    SaveLocationResponse,
    SimulateRequest,
    SimulateResponse,
)
from view.templating import templates

if TYPE_CHECKING:
    from bootstrap import AppContext
    from model.repositories.llm.llm_event_flavor_author import LlmEventFlavorAuthor
    from model.repositories.llm.llm_item_author import LlmItemAuthor
    from model.repositories.llm.llm_location_author import LlmLocationAuthor
    from model.repositories.llm.llm_result_text_parser import LlmResultTextParser
    from model.services.ports import EmbeddingPort

_logger = logging.getLogger("eventhorizon.admin_controller")


def register_admin_routes(
    fastapi_app: FastAPI,
    app_ctx: "AppContext",
    llm_location_author: "LlmLocationAuthor | None" = None,
    llm_item_author: "LlmItemAuthor | None" = None,
    llm_event_flavor_author: "LlmEventFlavorAuthor | None" = None,
    embedding: "EmbeddingPort | None" = None,
    llm_result_text_parser: "LlmResultTextParser | None" = None,
) -> None:
    @fastapi_app.get("/admin", response_class=HTMLResponse)
    def admin_index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse("admin.html", {"request": request})

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

    # ---------- 地图：AI 生成（可选，需要 llm_config.json 配好才真正调模型）----------

    @fastapi_app.post("/api/admin/generate_locations", response_model=GenerateLocationsResponse)
    def generate_locations(req: GenerateLocationsRequest) -> GenerateLocationsResponse:
        if llm_location_author is None:
            return GenerateLocationsResponse(ok=False, error="LLM 未配置（检查 eventhorizon/llm_config.json）")
        try:
            items = llm_location_author.generate_locations(req.kinds, req.count)
        except Exception as exc:  # 网络/超时/接口格式问题不该让整个请求 500——前端按 ok=False 回退到本地生成
            _logger.warning("LLM 生成地点失败：%s", exc)
            return GenerateLocationsResponse(ok=False, error=str(exc))
        return GenerateLocationsResponse(ok=True, items=[LlmLocationItemDTO(**it) for it in items])

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
        # 保存时预计算 name+description 的向量并缓存（README 1.4.1 的"录入时预计算"
        # 原则）——事件"结果"提到"获得某样东西"时，就是拿这份向量去做相似度匹配
        # （model/services/item_embedding_match.py），不在每次触发时现场编码全库。
        # LLM 向量化失败（没配置/网络/账户余额等）时退到本地向量化，不是直接放弃——
        # 物品名字/描述是名词短语，本地的字符词袋对这种比较还算有区分度（不像
        # predicate_text 那种数值条件判断，本地词袋在那边只会帮倒忙）。
        item_embedding = embed_with_fallback(embedding, f"{dto.name} {dto.description}".strip())
        app_ctx.items.save_item_def(
            ItemDef(
                item_id=dto.item_id, kind=kind, stackable=dto.stackable, unique=dto.unique,
                name=dto.name, description=dto.description, embedding=item_embedding,
            )
        )
        return SaveLocationResponse(ok=True)

    @fastapi_app.delete("/api/admin/items/{item_id}", response_model=SaveLocationResponse)
    def delete_item(item_id: str) -> SaveLocationResponse:
        if not app_ctx.items.delete_item_def(item_id):
            raise HTTPException(404, "物品不存在")
        return SaveLocationResponse(ok=True)

    @fastapi_app.post("/api/admin/generate_items", response_model=GenerateItemsResponse)
    def generate_items(req: GenerateItemsRequest) -> GenerateItemsResponse:
        if llm_item_author is None:
            return GenerateItemsResponse(ok=False, error="LLM 未配置（检查 eventhorizon/llm_config.json）")
        try:
            items = llm_item_author.generate_items(req.kinds, req.count, req.novel)
        except Exception as exc:  # 网络/超时/接口格式问题不该让整个请求 500——前端按 ok=False 报错，不拿本地内容凑数
            _logger.warning("LLM 生成物品失败：%s", exc)
            return GenerateItemsResponse(ok=False, error=str(exc))
        return GenerateItemsResponse(ok=True, items=[LlmItemItemDTO(**it) for it in items])

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
        # predicate_text -> predicate_embedding：编辑器不再让人手填这个向量，保存时
        # 用 EmbeddingPort 现算一次并缓存（README 1.4.1："录入时预计算"，不在每次
        # 触发时现场编码）。没配置 embedding 或调用失败都不能让保存这个动作本身
        # 失败——退化成空向量，运行时 fail-open 当无条件处理（matching.py）。
        predicate_text = str(raw.get("predicate_text") or "").strip()
        if predicate_text and embedding is not None:
            try:
                raw["predicate_embedding"] = embedding.embed(predicate_text)
            except Exception as exc:
                _logger.warning("predicate_text 向量化失败：%s", exc)
                raw["predicate_embedding"] = []
        else:
            raw["predicate_embedding"] = []
        # result_text -> result_pool：只有真的填了文字描述才尝试解析、并整体替换
        # result_pool；留空就是前端传回来的原样（旧数据或空列表），不去动它。
        result_text = str(raw.get("result_text") or "").strip()
        if result_text and llm_result_text_parser is not None:
            try:
                outcome = llm_result_text_parser.parse(result_text)
                result_pool = list(outcome.state_changes)
                item_result = _resolve_item_query(outcome.item_query, app_ctx, embedding)
                if item_result is not None:
                    result_pool.append(item_result)
                raw["result_pool"] = result_pool
            except Exception as exc:
                _logger.warning("result_text 解析失败：%s", exc)
        catalog = _build_catalog(app_ctx)
        defn, errors = validate_event_def(raw, catalog)
        if defn is None:
            return SaveEventResponse(ok=False, field_errors=[FieldErrorDTO(field=e.field, message=e.message) for e in errors])
        app_ctx.events.save_event_def(defn)
        _refresh_parser_if_needed(app_ctx)
        return SaveEventResponse(ok=True, event_id=defn.event_id)

    @fastapi_app.post("/api/admin/generate_events", response_model=GenerateEventsResponse)
    def generate_events(req: GenerateEventsRequest) -> GenerateEventsResponse:
        """AI 生成事件：模型出 tags/aliases/variants/weight/duration_shichen/
        cooldown_shichen/priority/result_pool（可参考小说式情节描述），数据完整度
        跟手工录入的事件一致；predicate 仍然固定 None（谓词是递归判别联合类型，
        模型编不出合法组合，宁可不生成也不生成错的），result_pool 已在
        LlmEventFlavorAuthor 里过滤成只剩安全的 state_change 条目。整条仍然过
        validate_event_def()——跟手工在编辑器里存草稿走的是同一条校验路径，不会
        因为是 AI 生成就绕开。校验没过的条目单独计入 field_errors，不影响其它
        条目正常入库。"""
        if llm_event_flavor_author is None:
            return GenerateEventsResponse(ok=False, error="LLM 未配置（检查 eventhorizon/llm_config.json）")
        try:
            flavors = llm_event_flavor_author.generate_event_flavors(req.description, req.count)
        except Exception as exc:
            _logger.warning("LLM 生成事件失败：%s", exc)
            return GenerateEventsResponse(ok=False, error=str(exc))

        catalog = _build_catalog(app_ctx)
        created_ids: list[str] = []
        field_errors: list[FieldErrorDTO] = []
        for flavor in flavors:
            result_pool = list(flavor.get("result_pool", []))
            item_result = _resolve_item_query(flavor.get("item_query", ""), app_ctx, embedding)
            if item_result is not None:
                result_pool.append(item_result)
            raw = {
                "event_id": "ai_" + uuid.uuid4().hex[:10],
                "applicable_locations": req.applicable_locations or ["*"],
                "predicate": None,
                "weight": flavor.get("weight", 1.0),
                "duration_shichen": flavor.get("duration_shichen", 1),
                "cooldown_shichen": flavor.get("cooldown_shichen", 0),
                "priority": flavor.get("priority", 5),
                "tags": flavor.get("tags", []),
                "aliases": flavor.get("aliases", []),
                "result_pool": result_pool,
                "variants": [{"text": text, "weight": 1.0} for text in flavor.get("variants", [])],
                "is_draft": True,
                "is_command": bool(flavor.get("aliases")),
            }
            defn, errors = validate_event_def(raw, catalog)
            if defn is not None:
                app_ctx.events.save_event_def(defn)
                created_ids.append(defn.event_id)
            else:
                field_errors.extend(FieldErrorDTO(field=f"{raw['event_id']}.{e.field}", message=e.message) for e in errors)
        if created_ids:
            _refresh_parser_if_needed(app_ctx)
        if not flavors:
            return GenerateEventsResponse(ok=False, error="AI 没能给出可用的文案（也可能是接口返回格式不对），换一段描述再试试")
        return GenerateEventsResponse(ok=bool(created_ids), event_ids=created_ids, field_errors=field_errors)

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
            AgentEventHistory(), request.sample_n, random.Random(), embedding,
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


def _resolve_item_query(item_query: str, app_ctx: "AppContext", embedding: "EmbeddingPort | None") -> dict | None:
    """"结果"文字描述里提到的物品（一句自然语言，比如"一把锋利的长剑"）解析成
    真实存在的 item_drop——用向量相似度在物品库里找语义最接近的一个（见
    model/services/item_embedding_match.py），找不到就是 None（宁可没有物品效果，
    也不把一个不相关的东西塞进背包）。LLM 向量化失败/未配置时退到本地词袋向量
    （embed_with_fallback），不像 predicate_text 那样直接放弃——物品名字/描述是
    名词短语，本地词袋对这种比较还有区分度。"""
    item_query = item_query.strip()
    if not item_query:
        return None
    from model.services.item_embedding_match import find_best_matching_item

    query_embedding = embed_with_fallback(embedding, item_query)
    matched = find_best_matching_item(app_ctx.items.list_all(), query_embedding)
    if matched is None:
        return None
    return {"kind": "item_drop", "item_id": matched.item_id, "n": 1}


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
        predicate_text=defn.predicate_text,
        predicate_embedding=list(defn.predicate_embedding),
        result_text=defn.result_text,
    )
