"""content/events/cangwu.py — 苍梧城事件（GAME_DESIGN §5.1 / §9.1，新手出生地，
生活/社交密集）。

金龙鱼是 README 2.2.1 玩法示例的落地：奇遇挂起 → ReplyOption 是解析兜底，不是
界面选项列表（GAME_DESIGN §2.2）。
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

ALL = (GOLDEN_FISH, GOLDEN_FISH_REVEAL, STREET_VENDOR, TAVERN_GOSSIP, PICKPOCKET, MARKET_BARGAIN)
