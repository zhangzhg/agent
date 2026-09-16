"""content/events/cangwu.py — 苍梧城事件（README §3.6 / §9.1，新手出生地，
生活/社交密集）。

金龙鱼是 README 2.2.1 玩法示例的落地：奇遇挂起 → ReplyOption 是解析兜底，不是
界面选项列表（README §3.2）。
"""
from __future__ import annotations

from model.domain.events import EventVariant, GameEventDef, ReplyOption
from model.domain.predicates import Predicate, PredicateGroup, PredicateType
from model.domain.results import ChainEvent, ItemDrop, StateChange, WriteCause

GOLDEN_FISH = GameEventDef(
    event_id="golden_fish",
    applicable_locations=("酒楼",),
    applicable_time=None,
    predicate=None,
    weight=3.0,
    duration_shichen=0,
    cooldown_shichen=0,
    max_trigger_per_agent=1,
    exclusive_tags=(),
    priority=5,
    tags=("奇遇",),
    aliases=(),
    result_pool=(),  # 只叙述、不结算——needs_reply 事件的结果全部挂在 ReplyOption 上
    variants=(EventVariant("水缸边围了一圈人，有人钓上一条金光闪闪的鱼，摊主吆喝着要卖。"),),
    reply_options=(
        ReplyOption(
            aliases=("买下来", "买了", "付钱"),
            results=(
                StateChange(field="money", delta=-20),
                ChainEvent(event_id="golden_fish_reveal"),
            ),
            response_text="你付了钱，摊主笑呵呵地把鱼包好递给你。",
        ),
    ),
    is_command=False,
    is_draft=False,
)

GOLDEN_FISH_REVEAL = GameEventDef(
    event_id="golden_fish_reveal",
    applicable_locations=("*",),
    applicable_time=None,
    predicate=None,
    weight=0.0,  # 只由 golden_fish 的 ReplyOption chain 触发，不参与常规粗筛抽取
    duration_shichen=0,
    cooldown_shichen=0,
    max_trigger_per_agent=1,
    exclusive_tags=(),
    priority=1,
    tags=("奇遇",),
    aliases=(),
    result_pool=(ItemDrop(item_id="dragon_scale", n=1), StateChange(field="money", delta=30), WriteCause(tag="际遇", target="金龙鱼", expires_years=None)),
    variants=(EventVariant("鱼入手中忽然温热，鳞片泛起微光——竟是一条尚未化形的小龙，留下一片龙鳞与谢礼后遁入水中不见。"),),
    is_command=False,
    is_draft=False,
)

STREET_VENDOR = GameEventDef(
    event_id="street_vendor",
    applicable_locations=("主街", "集市"),
    applicable_time=None,
    predicate=None,
    weight=2.0,
    duration_shichen=0,
    cooldown_shichen=24,
    max_trigger_per_agent=None,
    exclusive_tags=(),
    priority=5,
    tags=("生活",),
    aliases=(),
    result_pool=(StateChange(field="scene_focus", set_to="小贩"),),
    variants=(
        EventVariant("街边小贩支起摊子，吆喝着卖些针头线脑。"),
        EventVariant("糖葫芦的甜香飘过来，勾得路人频频回头。"),
    ),
    is_command=False,
    is_draft=False,
)

TAVERN_GOSSIP = GameEventDef(
    event_id="tavern_gossip",
    applicable_locations=("酒楼",),
    applicable_time=None,
    predicate=None,
    weight=2.0,
    duration_shichen=0,
    cooldown_shichen=24,
    max_trigger_per_agent=None,
    exclusive_tags=(),
    priority=5,
    tags=("社交", "奇遇"),
    aliases=(),
    result_pool=(StateChange(field="scene_focus", set_to="藏剑山门"),),
    variants=(
        EventVariant("邻座几人正议论，说藏剑山门近来在招收弟子。"),
        EventVariant("有人低声说黑风谷最近不太平，妖兽活动频繁。"),
    ),
    is_command=False,
    is_draft=False,
)

PICKPOCKET = GameEventDef(
    event_id="pickpocket",
    applicable_locations=("集市",),
    applicable_time=None,
    predicate=PredicateGroup("AND", (Predicate(PredicateType.MONEY_GTE, (5,)),)),
    weight=1.0,
    duration_shichen=0,
    cooldown_shichen=48,
    max_trigger_per_agent=None,
    exclusive_tags=(),
    priority=5,
    tags=("奇遇", "环境"),
    aliases=(),
    result_pool=(StateChange(field="money", delta=-5),),
    variants=(EventVariant("人群拥挤间，你觉得腰间一轻——摸了摸，钱袋竟被人摸走了几个钱。"),),
    is_command=False,
    is_draft=False,
)

MARKET_BARGAIN = GameEventDef(
    event_id="market_bargain",
    applicable_locations=("集市",),
    applicable_time=None,
    predicate=None,
    weight=1.5,
    duration_shichen=0,
    cooldown_shichen=24,
    max_trigger_per_agent=None,
    exclusive_tags=(),
    priority=5,
    tags=("生活",),
    aliases=(),
    result_pool=(ItemDrop(item_id="cloth_pouch", n=1),),
    variants=(EventVariant("摊主见你面善，多送了个小布袋。"),),
    is_command=False,
    is_draft=False,
)

TEAHOUSE_DEBATE = GameEventDef(
    event_id="teahouse_debate",
    applicable_locations=("酒楼",),
    applicable_time=None,
    predicate=None,
    weight=1.5,
    duration_shichen=0,
    cooldown_shichen=36,
    max_trigger_per_agent=None,
    exclusive_tags=(),
    priority=5,
    tags=("社交",),
    aliases=(),
    result_pool=(StateChange(field="scene_focus", set_to="辩论的客人"),),
    variants=(
        EventVariant("邻桌两位散修为了一句功法要义争得面红耳赤。"),
        EventVariant("有人拍案而起，说对方的修炼法门根本是歪门邪道。"),
        EventVariant("几位食客围着一张桌子，正为谁的境界更高争论不休。"),
    ),
    is_command=False,
    is_draft=False,
)

CHILDHOOD_FRIEND = GameEventDef(
    event_id="childhood_friend",
    applicable_locations=("主街",),
    applicable_time=None,
    predicate=None,
    weight=1.0,
    duration_shichen=0,
    cooldown_shichen=200,
    max_trigger_per_agent=1,
    exclusive_tags=(),
    priority=5,
    tags=("社交", "奇遇"),
    aliases=(),
    result_pool=(WriteCause(tag="知己", target="儿时旧友", expires_years=None),),
    variants=(
        EventVariant("一张熟悉的脸从人群里冒出来——是许久未见的儿时旧友，两人相视大笑。"),
        EventVariant("有人从背后拍你的肩膀，一回头竟是失散多年的旧相识。"),
    ),
    is_command=False,
    is_draft=False,
)

BEGGAR_KINDNESS = GameEventDef(
    event_id="beggar_kindness",
    applicable_locations=("主街", "集市"),
    applicable_time=None,
    predicate=PredicateGroup("AND", (Predicate(PredicateType.MONEY_GTE, (3,)),)),
    weight=1.0,
    duration_shichen=0,
    cooldown_shichen=72,
    max_trigger_per_agent=None,
    exclusive_tags=(),
    priority=5,
    tags=("社交",),
    aliases=(),
    result_pool=(StateChange(field="money", delta=-3), WriteCause(tag="恩情", target="街边乞儿", expires_years=15)),
    variants=(
        EventVariant("街角一个衣衫褴褛的孩子冲你伸出手，你随手给了些铜钱。"),
        EventVariant("一位老乞丐向你行了个礼，念叨着「善有善报」。"),
    ),
    is_command=False,
    is_draft=False,
)

LANTERN_NIGHT = GameEventDef(
    event_id="lantern_night",
    applicable_locations=("主街",),
    applicable_time=None,
    predicate=None,
    weight=1.0,
    duration_shichen=0,
    cooldown_shichen=48,
    max_trigger_per_agent=None,
    exclusive_tags=(),
    priority=5,
    tags=("环境", "生活"),
    aliases=(),
    result_pool=(StateChange(field="heart_demon", delta=-0.01),),
    variants=(
        EventVariant("满街灯笼次第亮起，映得青石板路暖融融的。"),
        EventVariant("孩童追逐着灯笼跑过，笑声在巷子里回荡。"),
    ),
    is_command=False,
    is_draft=False,
)

NEW_STALL_OWNER = GameEventDef(
    event_id="new_stall_owner",
    applicable_locations=("集市",),
    applicable_time=None,
    predicate=PredicateGroup("AND", (Predicate(PredicateType.MONEY_GTE, (3,)),)),
    weight=1.5,
    duration_shichen=0,
    cooldown_shichen=48,
    max_trigger_per_agent=None,
    exclusive_tags=(),
    priority=5,
    tags=("生活",),
    aliases=(),
    result_pool=(StateChange(field="money", delta=-3), ItemDrop(item_id="cloth_pouch", n=1)),
    variants=(
        EventVariant("新开张的小摊贩热情招呼，你随手买了个小玩意儿。"),
        EventVariant("摊主是个生面孔，吆喝声格外卖力，你凑趣买了点东西。"),
    ),
    is_command=False,
    is_draft=False,
)

ALL = (
    GOLDEN_FISH, GOLDEN_FISH_REVEAL, STREET_VENDOR, TAVERN_GOSSIP, PICKPOCKET, MARKET_BARGAIN,
    TEAHOUSE_DEBATE, CHILDHOOD_FRIEND, BEGGAR_KINDNESS, LANTERN_NIGHT, NEW_STALL_OWNER,
)
