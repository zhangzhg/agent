"""content/events/guixu.py — 归墟秘境事件（GAME_DESIGN §5.1：高境界限定，隐藏点位；
需先被神识扫描发现，见 model/services/exploration_service.py）。
"""
from __future__ import annotations

from model.domain.events import EventVariant, GameEventDef
from model.domain.predicates import Predicate, PredicateGroup, PredicateType
from model.domain.results import FlagSet, ItemDrop, StateChange, WriteCause

ANCIENT_RESONANCE = GameEventDef(
    event_id="ancient_resonance",
    applicable_locations=("秘境",),
    applicable_time=None,
    predicate=PredicateGroup("AND", (Predicate(PredicateType.REALM_GTE, (2,)),)),  # 筑基以上
    weight=2.0,
    duration_shichen=0,
    cooldown_shichen=48,
    max_trigger_per_agent=None,
    exclusive_tags=(),
    priority=5,
    tags=("奇遇",),
    aliases=(),
    result_pool=(StateChange(field="cultivation", delta=30),),
    variants=(EventVariant("秘境深处传来古老的共鸣，你静心感悟，修为竟有精进。"),),
    is_command=False,
    is_draft=False,
)

RUIN_TREASURE = GameEventDef(
    event_id="ruin_treasure",
    applicable_locations=("秘境",),
    applicable_time=None,
    predicate=PredicateGroup("AND", (Predicate(PredicateType.REALM_GTE, (2,)),)),
    weight=1.0,
    duration_shichen=0,
    cooldown_shichen=200,
    max_trigger_per_agent=1,
    exclusive_tags=(),
    priority=5,
    tags=("奇遇",),
    aliases=(),
    result_pool=(ItemDrop(item_id="ancient_token", n=1),),
    variants=(EventVariant("断壁残垣间，你找到一枚不知年岁的古老令牌。"),),
    is_command=False,
    is_draft=False,
)

VOID_WHISPER = GameEventDef(
    event_id="void_whisper",
    applicable_locations=("秘境",),
    applicable_time=None,
    predicate=None,
    weight=1.5,
    duration_shichen=0,
    cooldown_shichen=24,
    max_trigger_per_agent=None,
    exclusive_tags=(),
    priority=5,
    tags=("环境",),
    aliases=(),
    result_pool=(),
    variants=(EventVariant("秘境深处传来若有若无的低语，听不真切，令人心神不宁。"),),
    is_command=False,
    is_draft=False,
)

FORMATION_PUZZLE = GameEventDef(
    event_id="formation_puzzle",
    applicable_locations=("秘境",),
    applicable_time=None,
    predicate=PredicateGroup("AND", (Predicate(PredicateType.REALM_GTE, (2,)),)),
    weight=1.0,
    duration_shichen=0,
    cooldown_shichen=96,
    max_trigger_per_agent=1,
    exclusive_tags=(),
    priority=5,
    tags=("奇遇",),
    aliases=(),
    result_pool=(StateChange(field="cultivation", delta=20), StateChange(field="heart_demon", delta=-0.03)),
    variants=(EventVariant("地面浮现出一座古老的阵图，你顺着阵纹推演，竟窥得几分玄妙。"),),
    is_command=False,
    is_draft=False,
)

ECHO_OF_ANCESTOR = GameEventDef(
    event_id="echo_of_ancestor",
    applicable_locations=("秘境",),
    applicable_time=None,
    predicate=PredicateGroup("AND", (Predicate(PredicateType.REALM_GTE, (2,)),)),
    weight=1.0,
    duration_shichen=0,
    cooldown_shichen=200,
    max_trigger_per_agent=1,
    exclusive_tags=(),
    priority=5,
    tags=("社交", "奇遇"),
    aliases=(),
    result_pool=(WriteCause(tag="际遇", target="残留意念", expires_years=None),),
    variants=(EventVariant("一道模糊的残念在你脑海中一闪而过，似是某位前辈临终前的执念。"),),
    is_command=False,
    is_draft=False,
)

SPIRIT_BEAST_LAIR = GameEventDef(
    event_id="spirit_beast_lair",
    applicable_locations=("秘境",),
    applicable_time=None,
    predicate=PredicateGroup("AND", (Predicate(PredicateType.REALM_GTE, (2,)),)),
    weight=1.0,
    duration_shichen=0,
    cooldown_shichen=48,
    max_trigger_per_agent=None,
    exclusive_tags=(),
    priority=4,
    tags=("奇遇", "妖兽"),
    aliases=(),
    result_pool=(FlagSet(name="遭遇战斗"),),
    variants=(EventVariant("一头灵兽从洞穴深处探出头来，警惕地盯着你。（可以「动手」或「逃」）"),),
    is_command=False,
    is_draft=False,
)

ALL = (
    ANCIENT_RESONANCE, RUIN_TREASURE, VOID_WHISPER,
    FORMATION_PUZZLE, ECHO_OF_ANCESTOR, SPIRIT_BEAST_LAIR,
)
