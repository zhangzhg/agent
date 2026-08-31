"""view/retreat_view.py — 闭关结算摘要文案（GAME_DESIGN §4.3）。

结算摘要必须包含修为/寿元变化、期间被跳过的全局事件类型汇总，不逐条罗列。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from model.services.retreat_intent_parser import SHICHEN_PER_YEAR

if TYPE_CHECKING:
    from model.services.clock_service import RetreatSummary


def render_retreat_summary(summary: "RetreatSummary", before_realm: str, before_cultivation: float) -> str:
    years = summary.shichen_advanced / SHICHEN_PER_YEAR
    time_note = f"{years:.0f}年过去" if years >= 1 else "不过短短数日"
    lines = ["你闭下心来，运转周天……"]

    realm_note = (
        f"境界从 {before_realm} 突破到了 {summary.final_realm}"
        if summary.final_realm != before_realm
        else f"修为在 {summary.final_realm} 境内又精进了不少"
    )
    lines.append(
        f"{time_note}，{realm_note}"
        f"（修为 {before_cultivation:.0f} → {before_cultivation + summary.cultivation_gained:.0f}），"
        f"寿元损耗 {summary.lifespan_spent:.1f}。"
    )

    if summary.tidal_days_skipped:
        lines.append(f"期间恰好错过了 {summary.tidal_days_skipped} 次灵气潮汐。")

    if summary.interrupted_by_force:
        lines.append(f"闭关途中忽生变故——{summary.force_reason}，只得中断出关。")
    elif summary.stopped_at_target_realm:
        lines.append(f"一朝功成，你如愿踏入了 {summary.final_realm}，当即出关。")

    return "\n".join(lines)
