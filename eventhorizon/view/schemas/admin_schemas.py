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


class GenerateLocationsRequest(BaseModel):
    """地图编辑器"AI 生成"面板用：只让模型起名字/定类型，数值型属性由前端按 kind
    在固定区间内随机取——跟 LlmLocationAuthor 的职责划分一致。"""

    kinds: list[str]
    count: int = 5


class LlmLocationItemDTO(BaseModel):
    name: str
    kind: str


class GenerateLocationsResponse(BaseModel):
    ok: bool
    items: list[LlmLocationItemDTO] = []
    error: str | None = None


# ---------- 物品（Item）----------


class ItemDTO(BaseModel):
    item_id: str
    kind: str  # ItemKind 的值：food/pill/manual/material/gear
    name: str = ""
    description: str = ""
    stackable: bool = True
    unique: bool = False


class GenerateItemsRequest(BaseModel):
    """物品页"AI 生成"面板用：模型只起名字/写描述，stackable/unique 由前端按
    kind 套固定规则——跟 LlmItemAuthor 的职责划分一致。kinds 留空表示不限定
    类型，由 LlmItemAuthor 顶成完整的 ItemKind 集合自由发挥。novel 留空表示不
    特别参考某部小说的世界观/命名风格。"""

    kinds: list[str] = Field(default_factory=list)
    count: int = 5
    novel: str = ""


class LlmItemItemDTO(BaseModel):
    name: str
    kind: str
    description: str = ""


class GenerateItemsResponse(BaseModel):
    ok: bool
    items: list[LlmItemItemDTO] = []
    error: str | None = None


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
    predicate_text: str = ""
    # 触发条件的自然语言描述（编辑器表单用它替代 predicate JSON 输入框）——留空
    # 表示无条件；非空时后端会调 EmbeddingPort 算向量并存下来，运行时按向量相似度
    # 判定（model/services/matching.py），不再要求手填 predicate 结构化 JSON。
    predicate_embedding: list[float] = Field(default_factory=list)
    # 只读：predicate_text 对应的向量，由后端在保存时算好；前端不需要也不应该自己填。
    result_text: str = ""
    # "结果"的自然语言描述（编辑器表单用它替代 result_pool JSON 输入框）——保存时
    # 后端尝试解析出其中的数值得失写回 result_pool；解析不出/没配置 LLM 时纯当
    # 描述文字存着，不报错。


class SaveEventResponse(BaseModel):
    ok: bool
    event_id: str | None = None
    field_errors: list[FieldErrorDTO] = []


class GenerateEventsRequest(BaseModel):
    """事件页"AI 生成"面板用：description 是情节/小说式描述，供 LlmEventFlavorAuthor
    参考；留空表示不指定情节，交给 AI 自己构思场景（见 llm_event_flavor_author.py
    的 _build_prompt）。机制字段（weight/predicate/result_pool 等）由后端填安全
    默认值，模型只出 tags/aliases/variants 这些文字素材，最终仍然整条过
    validate_event_def()。"""

    description: str = ""
    applicable_locations: list[str] = Field(default_factory=lambda: ["*"])
    count: int = 3


class GenerateEventsResponse(BaseModel):
    ok: bool
    event_ids: list[str] = []
    field_errors: list[FieldErrorDTO] = []
    error: str | None = None


# ---------- 模拟触发沙盒（ARCHITECTURE §1.3.3 测试沙盒）----------


class SimulateRequest(BaseModel):
    event_id: str
    context_snapshot: dict[str, Any] = Field(default_factory=dict)
    sample_n: int = 100


class SimulateResponse(BaseModel):
    passed_coarse_filter: bool
    relative_weight_share: float
    hit_distribution: dict[str, int]
