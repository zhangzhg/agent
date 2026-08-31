"""content/events/commands.py — P0 命令型事件（GAME_DESIGN §3.1 表格 + §9.2 P0）。

move / retreat_start / inspect_npc 是系统命令，不在这里（ChatParser 内置识别，
PlayTurnService 特判处理，见 model/services/chat_parser.py 顶部注释）。
"""
from __future__ import annotations

from model.domain.events import EventVariant, GameEventDef, ReplyOption
from model.domain.predicates import Predicate, PredicateGroup, PredicateType
from model.domain.results import Check, FlagClear, StateChange, WriteCause
from model.services.handlers.result_pool_executor import NEXT_REALM_SENTINEL

EAT = GameEventDef(
    event_id="eat",
    applicable_locations=("*",),
    applicable_time=None,
    predicate=PredicateGroup("AND", (Predicate(PredicateType.MONEY_GTE, (2,)),)),
    weight=1.0,
    duration_shichen=1,
    cooldown_shichen=6,
    max_trigger_per_agent=None,
    exclusive_tags=(),
    priority=5,
    tags=("生活",),
    aliases=("吃饭", "去吃点东西", "果腹", "填饱肚子"),
    result_pool=(StateChange(field="money", delta=-2), StateChange(field="satiety", delta=20)),
    variants=(
        EventVariant("你随便找了个摊子，几口下肚，饱食感涌了上来。"),
        EventVariant("路边小店的吃食谈不上精致，倒也管饱。"),
        EventVariant("你掏钱买了些吃的，边走边吃，肚子总算不叫了。"),
    ),
    is_command=True,
    is_draft=False,
)

MEDITATE = GameEventDef(
    event_id="meditate",
    applicable_locations=("*",),
    applicable_time=None,
    predicate=None,
    weight=1.0,
    duration_shichen=2,
    cooldown_shichen=0,
    max_trigger_per_agent=None,
    exclusive_tags=(),
    priority=5,
    tags=("修炼",),
    aliases=("打坐", "运功", "修炼"),
    result_pool=(StateChange(field="cultivation", delta=5),),
    variants=(
        EventVariant("你盘膝而坐，运转周天，一丝灵气缓缓汇入丹田。"),
        EventVariant("闭目凝神，杂念渐消，修为略有精进。"),
        EventVariant("这一坐便是半个时辰，睁眼时只觉神清气爽。"),
    ),
    is_command=True,
    is_draft=False,
)

BREAKTHROUGH = GameEventDef(
    event_id="breakthrough",
    applicable_locations=("*",),
    applicable_time=None,
    # 谓词只能是静态阈值，没法按"当前境界该境界的具体修为需求"动态取数
    # （BalanceTable.cultivation_required_for 按境界各不相同，ATTR_GTE 无法引用它）；
    # 这里退而求其次，只要求"修炼过一段时间"，真正的门槛感来自 _breakthrough_probability
    # 本身偏低的成功率。完整的按境界动态阈值门控留给 V1 扩展专门的谓词类型。
    predicate=PredicateGroup("AND", (Predicate(PredicateType.ATTR_GTE, ("cultivation", 50)),)),
    weight=1.0,
    duration_shichen=1,
    cooldown_shichen=12,
    max_trigger_per_agent=None,
    exclusive_tags=("突破",),
    priority=3,
    tags=("修炼",),
    aliases=("突破", "冲击境界", "渡劫"),
    result_pool=(
        Check(
            kind="breakthrough",
            on_success=(StateChange(field="realm", set_to=NEXT_REALM_SENTINEL),),
            on_fail=(StateChange(field="heart_demon", delta=0.05),),
        ),
    ),
    variants=(
        EventVariant("你深吸一口气，向着境界壁垒发起冲击……"),
        EventVariant("周身灵气翻涌，这一次，你能突破吗？"),
    ),
    is_command=True,
    is_draft=False,
)

WATCH = GameEventDef(
    event_id="watch",
    applicable_locations=("*",),
    applicable_time=None,
    predicate=None,
    weight=1.0,
    duration_shichen=0,
    cooldown_shichen=0,
    max_trigger_per_agent=None,
    exclusive_tags=(),
    priority=5,
    tags=("生活",),
    aliases=("围观", "看看", "凑过去看"),
    result_pool=(),
    variants=(
        EventVariant("你凑近了些，看向{对象}。"),
        EventVariant("你打量了一圈四周，一时没什么特别的发现。"),
    ),
    is_command=True,
    is_draft=False,
)

APPRENTICE = GameEventDef(
    event_id="apprentice",
    applicable_locations=("山门",),
    applicable_time=None,
    predicate=PredicateGroup("AND", (Predicate(PredicateType.AGE_GTE, (6,)),)),
    weight=1.0,
    duration_shichen=2,
    cooldown_shichen=144,
    max_trigger_per_agent=None,
    exclusive_tags=(),
    priority=4,
    tags=("社交",),
    aliases=("拜师", "请求加入", "求收留"),
    result_pool=(
        Check(
            kind="combat",  # 借用同一套 clamp 检定作为"考较资质"的通过率，不额外发明公式
            on_success=(WriteCause(tag="师徒", target="藏剑山门", expires_years=None),),
            on_fail=(StateChange(field="heart_demon", delta=0.02),),
        ),
    ),
    variants=(
        EventVariant("守门弟子上下打量你一番，进去通报了。"),
        EventVariant("你说明来意，对方似乎有些犹豫。"),
    ),
    is_command=True,
    is_draft=False,
)

FIGHT = GameEventDef(
    event_id="fight",
    applicable_locations=("*",),
    applicable_time=None,
    predicate=PredicateGroup("AND", (Predicate(PredicateType.FLAG, ("遭遇战斗",)),)),
    weight=1.0,
    duration_shichen=1,
    cooldown_shichen=0,
    max_trigger_per_agent=None,
    exclusive_tags=(),
    priority=2,
    tags=("奇遇",),
    aliases=("动手", "打他", "出手"),
    result_pool=(
        FlagClear(name="遭遇战斗"),
        Check(
            kind="combat",
            on_success=(WriteCause(tag="手下败将", target="妖兽", expires_years=1),),
            on_fail=(StateChange(field="heart_demon", delta=0.1), StateChange(field="satiety", delta=-10)),
        ),
    ),
    variants=(EventVariant("你不再犹豫，迎了上去！"),),
    is_command=True,
    is_draft=False,
)

FLEE = GameEventDef(
    event_id="flee",
    applicable_locations=("*",),
    applicable_time=None,
    predicate=PredicateGroup("AND", (Predicate(PredicateType.FLAG, ("遭遇战斗",)),)),
    weight=1.0,
    duration_shichen=1,
    cooldown_shichen=0,
    max_trigger_per_agent=None,
    exclusive_tags=(),
    priority=2,
    tags=("奇遇",),
    aliases=("逃", "跑", "撤"),
    result_pool=(FlagClear(name="遭遇战斗"), StateChange(field="satiety", delta=-5)),
    variants=(EventVariant("你转身就跑，也不知道对方有没有追上来。"),),
    is_command=True,
    is_draft=False,
)

ALL = (EAT, MEDITATE, BREAKTHROUGH, WATCH, APPRENTICE, FIGHT, FLEE)
