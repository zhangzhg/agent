"""content/events/heifeng.py — 黑风谷事件（README §3.6：战斗/危险类事件，
妖兽出没；灵气潮汐"狂暴期"妖兽类事件权重 ×2，见 §4.2）。

qi_deviation 是走火入魔（force 级），由 BREAKTHROUGH 连续失败达阈值时 chain
触发（见 result_pool_executor._crosses_qi_deviation_threshold），event_id 必须
与 BalanceTable.breakthrough["qi_deviation_event_id"] 一致。
"""
from __future__ import annotations

from model.domain.events import EventVariant, GameEventDef
from model.domain.results import FlagSet, ItemDrop, StateChange, WriteCause

BEAST_AMBUSH = GameEventDef(
    event_id="beast_ambush",
    applicable_locations=("荒野",),
    applicable_time=None,
    # 没有"未处于遭遇战斗"这种否定谓词（白名单只有 AND/OR，没有 NOT），所以不做
    # "不能连续遇袭"的门控；FlagSet 本身幂等（agent.flags 是 set），重复置位无害。
    predicate=None,
    weight=3.0,
    duration_shichen=0,
    cooldown_shichen=24,
    max_trigger_per_agent=None,
    exclusive_tags=(),
    priority=4,
    tags=("奇遇", "妖兽"),
    aliases=(),
    result_pool=(FlagSet(name="遭遇战斗"),),
    variants=(EventVariant("草丛一阵异动，一头妖兽龇牙咆哮着扑了出来！（可以「动手」或「逃」）"),),
    is_command=False,
    is_draft=False,
)

FOREST_HERBS = GameEventDef(
    event_id="forest_herbs",
    applicable_locations=("荒野",),
    applicable_time=None,
    predicate=None,
    weight=2.0,
    duration_shichen=0,
    cooldown_shichen=24,
    max_trigger_per_agent=None,
    exclusive_tags=(),
    priority=5,
    tags=("奇遇",),
    aliases=(),
    result_pool=(ItemDrop(item_id="spirit_herb", n=1),),
    variants=(EventVariant("崖壁缝隙里，你发现几株野生的灵草。"),),
    is_command=False,
    is_draft=False,
)

WANDERING_CULTIVATOR = GameEventDef(
    event_id="wandering_cultivator",
    applicable_locations=("荒野",),
    applicable_time=None,
    predicate=None,
    weight=1.0,
    duration_shichen=0,
    cooldown_shichen=100,
    max_trigger_per_agent=None,
    exclusive_tags=(),
    priority=5,
    tags=("社交",),
    aliases=(),
    result_pool=(StateChange(field="scene_focus", set_to="散修"),),
    variants=(EventVariant("一名风尘仆仆的散修与你擦肩而过，点头致意。"),),
    is_command=False,
    is_draft=False,
)

STORM_WARNING = GameEventDef(
    event_id="storm_warning",
    applicable_locations=("荒野",),
    applicable_time=None,
    predicate=None,
    weight=1.0,
    duration_shichen=0,
    cooldown_shichen=48,
    max_trigger_per_agent=None,
    exclusive_tags=(),
    priority=5,
    tags=("环境",),
    aliases=(),
    result_pool=(),
    variants=(EventVariant("远处天色骤然阴沉，隐有雷声滚动，山雨欲来。"),),
    is_command=False,
    is_draft=False,
)

QI_DEVIATION = GameEventDef(
    event_id="qi_deviation",
    applicable_locations=("*",),
    applicable_time=None,
    predicate=None,
    weight=0.0,  # 只由 force 级 chain 触发（连续突破失败），不参与常规抽取
    duration_shichen=6,
    cooldown_shichen=0,
    max_trigger_per_agent=None,
    exclusive_tags=(),
    priority=0,
    tags=("天劫",),
    aliases=(),
    result_pool=(StateChange(field="heart_demon", delta=0.1), StateChange(field="cultivation", delta=-20)),
    variants=(EventVariant("气血翻涌，心魔趁虚而入——你陷入了短暂的癫狂，浑浑噩噩了一阵才缓过神来。"),),
    is_command=False,
    is_draft=False,
)

HUNTER_CAMP = GameEventDef(
    event_id="hunter_camp",
    applicable_locations=("荒野",),
    applicable_time=None,
    predicate=None,
    weight=1.5,
    duration_shichen=0,
    cooldown_shichen=48,
    max_trigger_per_agent=None,
    exclusive_tags=(),
    priority=5,
    tags=("社交", "生活"),
    aliases=(),
    result_pool=(StateChange(field="satiety", delta=8),),
    variants=(
        EventVariant("一处猎户扎的临时营地还留着余温，你分了些烤肉充饥。"),
        EventVariant("路过的猎户见你面生，招呼你一起烤了会儿火，分了口吃食。"),
    ),
    is_command=False,
    is_draft=False,
)

TRAP_INJURY = GameEventDef(
    event_id="trap_injury",
    applicable_locations=("荒野",),
    applicable_time=None,
    predicate=None,
    weight=1.0,
    duration_shichen=0,
    cooldown_shichen=48,
    max_trigger_per_agent=None,
    exclusive_tags=(),
    priority=5,
    tags=("奇遇",),
    aliases=(),
    result_pool=(StateChange(field="satiety", delta=-5), StateChange(field="heart_demon", delta=0.01)),
    variants=(EventVariant("脚下一软，你踩进了猎户设下的陷阱，费了好一番功夫才脱身。"),),
    is_command=False,
    is_draft=False,
)

BEAST_TRACKS = GameEventDef(
    event_id="beast_tracks",
    applicable_locations=("荒野",),
    applicable_time=None,
    predicate=None,
    weight=1.0,
    duration_shichen=0,
    cooldown_shichen=24,
    max_trigger_per_agent=None,
    exclusive_tags=(),
    priority=5,
    tags=("环境",),
    aliases=(),
    result_pool=(),
    variants=(
        EventVariant("地上有一串还未干涸的兽爪印，看起来不小。"),
        EventVariant("林间隐约传来低沉的兽吼，听不出方向。"),
    ),
    is_command=False,
    is_draft=False,
)

FELLOW_SURVIVOR = GameEventDef(
    event_id="fellow_survivor",
    applicable_locations=("荒野",),
    applicable_time=None,
    predicate=None,
    weight=1.0,
    duration_shichen=0,
    cooldown_shichen=100,
    max_trigger_per_agent=None,
    exclusive_tags=(),
    priority=5,
    tags=("社交",),
    aliases=(),
    result_pool=(WriteCause(tag="患难", target="谷中幸存者", expires_years=10),),
    variants=(EventVariant("你救下一位被妖兽逼到绝境的旅人，对方连声道谢。"),),
    is_command=False,
    is_draft=False,
)

ALL = (
    BEAST_AMBUSH, FOREST_HERBS, WANDERING_CULTIVATOR, STORM_WARNING, QI_DEVIATION,
    HUNTER_CAMP, TRAP_INJURY, BEAST_TRACKS, FELLOW_SURVIVOR,
)
