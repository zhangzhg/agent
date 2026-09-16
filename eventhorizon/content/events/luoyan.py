"""content/events/luoyan.py — 落雁镇事件（README §3.6：集市为主，经济类事件
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
    # 恩情这条因果链目前没有后续事件消费它——单独留着不会显式生效，跟旁边
    # cangwu.py 里同类的乐善好施事件一样，因果钩子之外总要配一条玩家当场就能
    # 看见的效果（StateChange/ItemDrop），不能让"事件触发了"和"什么都没发生"
    # 划等号。
    result_pool=(StateChange(field="money", delta=3), WriteCause(tag="恩情", target="走失孩童家人", expires_years=10)),
    variants=(EventVariant("你顺手帮一个走失的孩童找到了家人，对方千恩万谢，塞给你几两银子作谢礼。"),),
    is_command=False,
    is_draft=False,
)

SILK_MERCHANT = GameEventDef(
    event_id="silk_merchant",
    applicable_locations=("集市",),
    applicable_time=None,
    predicate=PredicateGroup("AND", (Predicate(PredicateType.MONEY_GTE, (8,)),)),
    weight=1.5,
    duration_shichen=0,
    cooldown_shichen=60,
    max_trigger_per_agent=None,
    exclusive_tags=(),
    priority=5,
    tags=("生活",),
    aliases=(),
    result_pool=(StateChange(field="money", delta=-8), ItemDrop(item_id="cloth_pouch", n=1)),
    variants=(
        EventVariant("绸缎庄的伙计极力推销一匹新到的料子，你被说动买了些。"),
        EventVariant("布庄老板娘手脚麻利地给你裁了块布料，说是压箱底的好货。"),
    ),
    is_command=False,
    is_draft=False,
)

BANDIT_RUMOR = GameEventDef(
    event_id="bandit_rumor",
    applicable_locations=("集市", "城市"),
    applicable_time=None,
    predicate=None,
    weight=1.5,
    duration_shichen=0,
    cooldown_shichen=48,
    max_trigger_per_agent=None,
    exclusive_tags=(),
    priority=5,
    tags=("社交", "奇遇"),
    aliases=(),
    result_pool=(StateChange(field="scene_focus", set_to="黑风谷"),),
    variants=(
        EventVariant("镖师们聚在一起低声议论，说黑风谷那边又出了妖兽伤人的事。"),
        EventVariant("有人说前几日一支商队在黑风谷附近折损了不少货物。"),
    ),
    is_command=False,
    is_draft=False,
)

OLD_FRIEND_LETTER = GameEventDef(
    event_id="old_friend_letter",
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
    result_pool=(WriteCause(tag="知己", target="远方旧友", expires_years=None),),
    variants=(EventVariant("驿站送来一封辗转多时的书信，是一位远方旧友的问候。"),),
    is_command=False,
    is_draft=False,
)

APPRAISAL_MISHAP = GameEventDef(
    event_id="appraisal_mishap",
    applicable_locations=("集市",),
    applicable_time=None,
    predicate=PredicateGroup("AND", (Predicate(PredicateType.HAS_ITEM, ("cloth_pouch",)),)),
    weight=1.0,
    duration_shichen=0,
    cooldown_shichen=96,
    max_trigger_per_agent=1,
    exclusive_tags=(),
    priority=5,
    tags=("奇遇",),
    aliases=(),
    result_pool=(ItemDrop(item_id="gold", n=1),),
    variants=(EventVariant("鉴宝师翻看你随身的布袋，惊讶地说里面混进了一件金饰。"),),
    is_command=False,
    is_draft=False,
)

ALL = (
    RARE_HERB_DEAL, CARAVAN_ARRIVAL, COUNTERFEIT_PILL, DEBT_COLLECTOR, LOST_CHILD,
    SILK_MERCHANT, BANDIT_RUMOR, OLD_FRIEND_LETTER, APPRAISAL_MISHAP,
)
