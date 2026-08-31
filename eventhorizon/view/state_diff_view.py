"""view/state_diff_view.py — 结构化状态差分的对外展现格式（对应 README §6）。

DTO 只做字段形状，校验在 model。只消费 AppliedDiff，不碰 Agent / PipelineContext。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from model.domain.diff import AppliedDiff


@dataclass
class StateDiffView:
    attr_changes: list[tuple[str, float]] = field(default_factory=list)
    realm_set: str | None = None
    location_set: str | None = None
    items_gained: list[tuple[str, int]] = field(default_factory=list)
    items_lost: list[tuple[str, int]] = field(default_factory=list)
    flags_gained: list[str] = field(default_factory=list)
    flags_lost: list[str] = field(default_factory=list)
    time_passed_shichen: int = 0

    @staticmethod
    def from_applied_diff(diff: "AppliedDiff | None") -> "StateDiffView":
        if diff is None:
            return StateDiffView()
        return StateDiffView(
            attr_changes=list(diff.attr_deltas),
            realm_set=diff.realm_set,
            location_set=diff.location_set,
            items_gained=list(diff.items_add),
            items_lost=list(diff.items_remove),
            flags_gained=list(diff.flags_set),
            flags_lost=list(diff.flags_clear),
            time_passed_shichen=diff.time_shichen_delta,
        )

    def to_summary_lines(self) -> list[str]:
        """给纯文本 UI 用的一行行摘要，如"金钱 -5""获得 玉佩 x1"。"""
        lines = []
        for name, delta in self.attr_changes:
            sign = "+" if delta >= 0 else ""
            lines.append(f"{name} {sign}{delta:g}")
        if self.realm_set:
            lines.append(f"境界 → {self.realm_set}")
        if self.location_set:
            lines.append(f"地点 → {self.location_set}")
        for item_id, n in self.items_gained:
            lines.append(f"获得 {item_id} x{n}")
        for item_id, n in self.items_lost:
            lines.append(f"失去 {item_id} x{n}")
        return lines
