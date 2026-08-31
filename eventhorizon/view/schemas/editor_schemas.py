"""view/schemas/editor_schemas.py — 事件录入编辑器的请求/响应 DTO（对应 README
1.3.3 / §6）。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SaveEventDraftRequest:
    """编辑器保存草稿：原始 dict 结构与 event_validation.validate_event_def 的入参
    一致，避免"编辑器传一套、校验读另一套"。"""

    raw_event: dict


@dataclass
class SaveEventDraftResponse:
    ok: bool
    event_id: str | None = None
    field_errors: list[dict] = field(default_factory=list)  # [{"field": ..., "message": ...}, ...]


@dataclass
class SimulateTriggerRequest:
    """录入页"模拟触发"沙盒：一份测试用快照 + 采样次数。"""

    event_id: str
    context_snapshot: dict  # {地点, 时间, 境界, 金钱…}
    sample_n: int = 100


@dataclass
class SimulateTriggerResponse:
    passed_coarse_filter: bool
    relative_weight_share: float
    hit_distribution: dict[str, int]  # event_id -> 命中次数（同池其它候选一并统计）


@dataclass
class GenerateDraftRequest:
    """录入页"用描述生成事件"：见 README 1.3.4。"""

    description: str
    constraints: dict = field(default_factory=dict)


@dataclass
class GenerateDraftResponse:
    drafts: list[dict] = field(default_factory=list)  # 已过校验、is_draft=True 的事件字典
    rejected: list[dict] = field(default_factory=list)  # 标错字段、未入库的原始条目
