"""content/events/luoyan.py — 落雁镇事件（GAME_DESIGN §5.1：集市为主，经济类事件
密集）。
"""
from __future__ import annotations

from model.domain.events import EventVariant, GameEventDef
from model.domain.predicates import Predicate, PredicateGroup, PredicateType
from model.domain.results import ItemDrop, StateChange, WriteCause

RARE_HERB_DEAL = GameEventDef(
    event_id="rare_herb_deal",
    applicable_locations=("集市",),
    applicable_time=None,
    predicate=PredicateGroup("AND", (Predicate(PredicateType.MONEY_GTE, (15,)),)),
    weight=2.0,
    duration_shichen=0,
    cooldown_shichen=48,
    max_trigger_per_agent=None,
    exclusive_tags=(),
    priority=5,
    tags=("生活",),
    aliases=(),
    result_pool=(StateChange(field="money", delta=-15), ItemDrop(item_id="spirit_herb", n=1)),
    variants=(EventVariant("药材商摆出一株带着灵光的草药，你出价买了下来。"),),
    is_command=False,
    is_draft=False,
)

CARAVAN_ARRIVAL = GameEventDef(
    event_id="caravan_arrival",
    applicable_locations=("集市", "城市"),
    applicable_time=None,
    predicate=None,
    weight=1.5,
    duration_shichen=0,
    cooldown_shichen=72,
    max_trigger_per_agent=None,
    exclusive_tags=(),
    priority=5,
    tags=("生活", "奇遇"),
    aliases=(),
    result_pool=(StateChange(field="scene_focus", set_to="商队"),),
    variants=(EventVariant("一支镖局商队进了镇子，车马喧闹，引得路人纷纷驻足。"),),
    is_command=False,
    is_draft=False,
)

COUNTERFEIT_PILL = GameEventDef(
    event_id="counterfeit_pill",
    applicable_locations=("集市",),
    applicable_time=None,
    predicate=PredicateGroup("AND", (Predicate(PredicateType.MONEY_GTE, (20,)),)),
    weight=1.0,
    duration_shichen=0,
    cooldown_shichen=96,
    max_trigger_per_agent=1,
    exclusive_tags=(),
    priority=5,
    tags=("奇遇",),
    aliases=(),
    result_pool=(StateChange(field="money", delta=-20),),
    variants=(EventVariant("小贩信誓旦旦说这是「筑基丹」，你掏钱买下——回头细看，多半是假的。"),),
    is_command=False,
    is_draft=False,
)

DEBT_COLLECTOR = GameEventDef(
    event_id="debt_collector",
    applicable_locations=("城市",),
    applicable_time=None,
    predicate=None,
    weight=1.0,
    duration_shichen=0,
    cooldown_shichen=200,
    max_trigger_per_agent=1,
    exclusive_tags=(),
    priority=5,
    tags=("社交",),
    aliases=(),
    result_pool=(WriteCause(tag="欠债", target="镖局", expires_years=5),),
    variants=(EventVariant("镖局的人拦住你，说你祖上欠了笔旧账，改日要来讨要。"),),
    is_command=False,
    is_draft=False,
)

LOST_CHILD = GameEventDef(
    event_id="lost_child",
    applicable_locations=("集市", "城市"),
    applicable_time=None,
    predicate=None,
    weight=1.5,
    duration_shichen=0,
    cooldown_shichen=72,
    max_trigger_per_agent=None,
    exclusive_tags=(),
    priority=5,
    tags=("社交",),
    aliases=(),
    result_pool=(WriteCause(tag="恩情", target="走失孩童家人", expires_years=10),),
    variants=(EventVariant("你顺手帮一个走失的孩童找到了家人，对方千恩万谢。"),),
    is_command=False,
    is_draft=False,
)

ALL = (RARE_HERB_DEAL, CARAVAN_ARRIVAL, COUNTERFEIT_PILL, DEBT_COLLECTOR, LOST_CHILD)
