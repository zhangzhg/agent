"""model/services/npc_query_service.py — 只读 NPC 信息卡查询（GAME_DESIGN §3.1 /
§6.3）。

"打听{NPC}"是只读查询命令：不改状态、不进 AgentEventHistory、不消耗回合，因此不
经 PlayTurnService，controller 直接调这里。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from model.domain.agent import Agent, Biography
    from model.domain.time import GameTime


@dataclass
class RelationLine:
    tag: str  # "仇人" / "恩人" / "师徒"…
    expires_in_years: int | None = None  # None 表示无过期


@dataclass
class NpcInfoCard:
    """对应 §6.3 的信息卡：出身 / 现状 / 与你的关系 / 生平。"""

    name: str
    origin: str
    current_status: str
    biography_line: str
    relations: list[RelationLine] = field(default_factory=list)

    def has_cause_record(self) -> bool:
        return bool(self.relations)


def build_npc_info_card(
    npc: "Agent",
    viewer: "Agent",
    biography: "Biography | None",
    now: "GameTime",
    current_status: str = "",
) -> NpcInfoCard:
    """§6.3："打听王麻子"返回只读卡片；有 CauseLink 时追加关系行，带过期倒计时。"""
    from model.services.biography_service import template_biography_line

    line = biography.epitaph() if biography is not None and biography.entries else template_biography_line(npc)
    relations = []
    for cause in npc.causes:
        if cause.target != viewer.agent_id:
            continue
        if cause.is_expired(now):
            continue
        expires_in_years = None
        if cause.expires_at is not None:
            from model.services.retreat_intent_parser import SHICHEN_PER_YEAR

            remaining_shichen = now.shichen_until(cause.expires_at)
            expires_in_years = max(0, round(remaining_shichen / SHICHEN_PER_YEAR))
        relations.append(RelationLine(tag=cause.tag, expires_in_years=expires_in_years))

    return NpcInfoCard(
        name=npc.agent_id,
        origin=npc.origin or "来历不明",
        current_status=current_status or f"现居{npc.location_id}",
        biography_line=line,
        relations=relations,
    )
