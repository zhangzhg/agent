"""model/services/biography_service.py — NPC 履历模拟（对应 README 1.5.1 /
GAME_DESIGN §6.2，ARCHITECTURE §4.13 表格已预留此文件，V1）。

模板一句话：未展开细履历的 NPC，用固定句式 + 随机填槽拼接，不经过事件库随机抽取。
细履历：仅对同城 / 有未过期 CauseLink / 被查询过的 NPC 展开，真实从事件库随机抽取
关键事件（步数上限 8），写入 Biography 事件流——因为走的是同一套 GameEventDef
随机接龙，允许比模板更离谱。
"""
from __future__ import annotations

import random
from typing import TYPE_CHECKING

from model.domain.agent import Biography
from model.services.matching import MatchContext, coarse_filter, reweight_and_pick

if TYPE_CHECKING:
    from model.domain.agent import Agent
    from model.domain.time import GameTime
    from model.services.ports import EventRepository

MAX_DETAILED_STEPS = 8

_AGE_BRACKETS = ((0, 12, "总角"), (12, 20, "束发"), (20, 30, "弱冠"), (30, 50, "而立"), (50, 200, "知命"))
_EVENT_TYPE_PHRASES = (
    "因资质平庸被逐出师门",
    "行走江湖闯出些名声",
    "在一场变故里失去至亲",
    "偶然习得一门手艺",
    "云游四方一无所获",
)
_OCCUPATION_BY_ORIGIN = {
    "商贾": "在坊市经营小买卖",
    "农家": "在乡下侍弄几亩薄田",
    "散修": "四处云游未曾定所",
    "宗门弟子": "于门中打理杂务",
}
_DEFAULT_OCCUPATION = "浪迹天涯为生"


def age_bracket_label(age: int) -> str:
    for lo, hi, label in _AGE_BRACKETS:
        if lo <= age < hi:
            return label
    return "耄耋"


def template_biography_line(npc: "Agent", rng: random.Random | None = None) -> str:
    """§6.2 模板一句话：固定句式 + 随机填槽，不经过事件库。
    示例："王麻子，二十岁因资质平庸被逐出师门，如今在坊市摆摊算卦为生。"""
    rng = rng or random.Random()
    event_phrase = rng.choice(_EVENT_TYPE_PHRASES)
    occupation = _OCCUPATION_BY_ORIGIN.get(npc.origin, _DEFAULT_OCCUPATION)
    return f"{npc.agent_id}，{npc.age}岁{event_phrase}，如今{occupation}。"


def should_use_detailed_biography(npc: "Agent", viewer_location_id: str, has_been_queried: bool) -> bool:
    """README 1.5.1：仅对同城、带未过期 CauseLink、或玩家查询过的 NPC 展开细履历；
    其余用模板一句话。"""
    return npc.location_id == viewer_location_id or bool(npc.causes) or has_been_queried


def generate_detailed_biography(
    npc: "Agent", events: "EventRepository", rng: random.Random, now: "GameTime"
) -> Biography:
    """真实从事件库随机抽取关键事件（步数上限 8），写入 Biography 事件流。
    这会顺带更新 npc.event_history，避免 NPC 的"人生"和玩家撞见的事件毫无关联。"""
    biography = Biography()
    pool = [e for e in events.load_event_defs(npc.location_type) if not e.is_command]
    for _ in range(MAX_DETAILED_STEPS):
        mctx = MatchContext(
            location=npc.location_id,
            location_type=npc.location_type,
            time_shichen=now.shichen,
            now=now,
            age=npc.age,
            realm=npc.realm,
            money=npc.money,
            causes=npc.causes,
        )
        candidates = coarse_filter(pool, mctx, npc.as_eval_context(), npc.event_history)
        picked = reweight_and_pick(candidates, npc.event_history, rng)
        if picked is None:
            break
        text = picked.variants[0].text if picked.variants else picked.event_id
        biography.append(now, text, picked.event_id)
        npc.event_history.record(picked.event_id, now, picked.tags, 0)
    return biography
