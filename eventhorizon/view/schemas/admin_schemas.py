"""view/schemas/admin_schemas.py — 录入编辑器（地图/城市/物品/事件）的 Web API
请求/响应模型（对应 ARCHITECTURE §1.3.3 / GAME_DESIGN §9.3）。

跟 web_schemas.py 一样：Pydantic 只用于 FastAPI 请求校验，不进 model 包。事件的
predicate / result_pool / reply_options 用原始 dict——那正是
model/services/event_validation.py 校验 + model/repositories/codec.py 序列化
共用的同一套 JSON 判别字段格式（"kind"/"type"），编辑器、LLM 草稿、SQLite 落盘
三处读同一套结构，这里复用而不是再发明一套。
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class FieldErrorDTO(BaseModel):
    field: str
    message: str


# ---------- 地图 / 城市（Location / Route）----------


class LocationDTO(BaseModel):
    location_id: str
    name: str
    kind: str  # LocationKind 的值，如 "城市" / "荒野" / "秘境"
    location_type: str  # 粗筛 / 谓词 location_type() 用的匹配键，如 "酒楼"
    x: float = 0.0
    y: float = 0.0
    qi_density: float = 1.0
    danger_level: float = 0.0
    condition: str = "完好"
    parent_location_id: str | None = None
    hidden: bool = False
    concealment: float = 0.0
    discovered: bool = False


class RouteDTO(BaseModel):
    from_id: str
    to_id: str
    move_cost_shichen: int = 1
    bidirectional: bool = True


class SaveLocationResponse(BaseModel):
    ok: bool
    field_errors: list[FieldErrorDTO] = []


# ---------- 物品（Item）----------


class ItemDTO(BaseModel):
    item_id: str
    kind: str  # ItemKind 的值：food/pill/manual/material/gear
    name: str = ""
    description: str = ""
    stackable: bool = True
    unique: bool = False


# ---------- 事件（GameEventDef）----------


class EventSummaryDTO(BaseModel):
    """事件列表用的精简视图（ARCHITECTURE §1.3.3："事件列表：筛选/搜索/标签/状态"）。"""

    event_id: str
    tags: list[str]
    applicable_locations: list[str]
    is_command: bool
    is_draft: bool
    weight: float


class EventDetailDTO(BaseModel):
    """完整事件定义，字段名与 codec.event_def_to_dict / event_validation.validate_event_def
    的 raw dict 结构一一对应——保存时直接把这个模型的 dict() 喂给 validate_event_def，
    不用再转换一次，从根上避免"编辑器一套、运行时一套"。"""

    event_id: str
    applicable_locations: list[str] = Field(default_factory=lambda: ["*"])
    applicable_time: list[int] | None = None
    predicate: dict[str, Any] | None = None
    weight: float = 1.0
    duration_shichen: int = 1
    cooldown_shichen: int = 0
    max_trigger_per_agent: int | None = None
    exclusive_tags: list[str] = Field(default_factory=list)
    priority: int = 5
    tags: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    result_pool: list[dict[str, Any]] = Field(default_factory=list)
    variants: list[dict[str, Any]] = Field(default_factory=list)
    reply_options: list[dict[str, Any]] = Field(default_factory=list)
    novelty_curve_override: dict[str, Any] | None = None
    scenario_ref: str | None = None
    is_draft: bool = True
    is_command: bool = False


class SaveEventResponse(BaseModel):
    ok: bool
    event_id: str | None = None
    field_errors: list[FieldErrorDTO] = []


# ---------- 模拟触发沙盒（ARCHITECTURE §1.3.3 测试沙盒）----------


class SimulateRequest(BaseModel):
    event_id: str
    context_snapshot: dict[str, Any] = Field(default_factory=dict)
    sample_n: int = 100


class SimulateResponse(BaseModel):
    passed_coarse_filter: bool
    relative_weight_share: float
    hit_distribution: dict[str, int]
