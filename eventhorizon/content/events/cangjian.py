"""content/events/cangjian.py — 藏剑山门事件（GAME_DESIGN §5.1：拜师、修炼类事件；
灵气浓度 0.7）。
"""
from __future__ import annotations

from model.domain.events import EventVariant, GameEventDef
from model.domain.predicates import Predicate, PredicateGroup, PredicateType
from model.domain.results import ItemDrop, StateChange, WriteCause

SECT_TRAINING = GameEventDef(
    event_id="sect_training",
    applicable_locations=("山门",),
    applicable_time=None,
    predicate=PredicateGroup("AND", (Predicate(PredicateType.FLAG, ("有门派归属",)),)),
    weight=2.0,
    duration_shichen=0,
    cooldown_shichen=24,
    max_trigger_per_agent=None,
    exclusive_tags=(),
    priority=5,
    tags=("修炼",),
    aliases=(),
    result_pool=(StateChange(field="cultivation", delta=8),),
    variants=(EventVariant("师兄弟们互相印证心得，你也从中获益不少。"),),
    is_command=False,
    is_draft=False,
)

ELDER_INSIGHT = GameEventDef(
    event_id="elder_insight",
    applicable_locations=("山门",),
    applicable_time=None,
    predicate=PredicateGroup("AND", (Predicate(PredicateType.FLAG, ("有门派归属",)),)),
    weight=1.0,
    duration_shichen=0,
    cooldown_shichen=200,
    max_trigger_per_agent=None,
    exclusive_tags=(),
    priority=5,
    tags=("修炼", "奇遇"),
    aliases=(),
    result_pool=(StateChange(field="cultivation", delta=15), StateChange(field="heart_demon", delta=-0.02)),
    variants=(EventVariant("一位长老偶然指点了你一句，如醍醐灌顶，你对功法的理解又深了一层。"),),
    is_command=False,
    is_draft=False,
)

SECT_RIVALRY = GameEventDef(
    event_id="sect_rivalry",
    applicable_locations=("山门",),
    applicable_time=None,
    predicate=PredicateGroup("AND", (Predicate(PredicateType.FLAG, ("有门派归属",)),)),
    weight=1.0,
    duration_shichen=0,
    cooldown_shichen=96,
    max_trigger_per_agent=None,
    exclusive_tags=(),
    priority=5,
    tags=("社交",),
    aliases=(),
    result_pool=(WriteCause(tag="心结", target="同门师兄", expires_years=3),),
    variants=(EventVariant("同门师兄弟在切磋名次上与你起了争执，气氛一时有些僵。"),),
    is_command=False,
    is_draft=False,
)

FOUND_MANUAL = GameEventDef(
    event_id="found_manual",
    applicable_locations=("山门",),
    applicable_time=None,
    predicate=None,
    weight=1.0,
    duration_shichen=0,
    cooldown_shichen=300,
    max_trigger_per_agent=1,
    exclusive_tags=(),
    priority=5,
    tags=("奇遇",),
    aliases=(),
    result_pool=(ItemDrop(item_id="basic_manual", n=1),),
    variants=(EventVariant("藏经阁外的角落里，你捡到一本无人认领的基础功法残卷。"),),
    is_command=False,
    is_draft=False,
)

MOUNTAIN_GATE_TEST = GameEventDef(
    event_id="mountain_gate_test",
    applicable_locations=("山门",),
    applicable_time=None,
    predicate=PredicateGroup("AND", (Predicate(PredicateType.FLAG, ("有门派归属",)),)),
    weight=1.0,
    duration_shichen=0,
    cooldown_shichen=500,
    max_trigger_per_agent=1,
    exclusive_tags=(),
    priority=5,
    tags=("修炼", "社交"),
    aliases=(),
    result_pool=(WriteCause(tag="知己", target="同门师妹", expires_years=None),),
    variants=(EventVariant("一场入门试炼后，你与一位师妹并肩而立，相视一笑，算是相熟了。"),),
    is_command=False,
    is_draft=False,
)

ALL = (SECT_TRAINING, ELDER_INSIGHT, SECT_RIVALRY, FOUND_MANUAL, MOUNTAIN_GATE_TEST)
