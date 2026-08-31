"""view/npc_info_card_view.py — NPC 信息卡的文本渲染（GAME_DESIGN §6.3）。"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from model.services.npc_query_service import NpcInfoCard


def render_npc_info_card(card: "NpcInfoCard") -> str:
    lines = [
        f"┌ {card.name} ─────────────┐",
        f"│ 出身：{card.origin}",
        f"│ 现状：{card.current_status}",
    ]
    if card.relations:
        for rel in card.relations:
            suffix = f"（{rel.expires_in_years}年内有效）" if rel.expires_in_years is not None else ""
            lines.append(f"│ 与你的关系：{rel.tag}{suffix}")
    else:
        lines.append("│ 与你的关系：无因果记录")
    lines.append(f"│ 生平：{card.biography_line}")
    lines.append("└──────────────────────┘")
    return "\n".join(lines)
