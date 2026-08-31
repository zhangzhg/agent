"""model/services/matching.py — 两阶段匹配 + 新鲜感机制（对应 README 1.4.2 / 1.4.3）。

reweight_and_pick 只做规则新颖度；V2 的向量新颖度以同一函数签名的装饰器/包装形式
叠加一个相似度乘子，不改这个函数本身（1.4.3"是同一步的两个乘子，不是两套系统"）。
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from model.domain.agent import AgentEventHistory
    from model.domain.cause import CauseLink
    from model.domain.events import GameEventDef
    from model.domain.predicates import EvalContext
    from model.domain.time import GameTime


@dataclass
class MatchContext:
    location: str
    location_type: str
    time_shichen: int
    now: "GameTime"
    age: int
    realm: str
    money: int
    causes: list["CauseLink"]


def coarse_filter(
    pool: list["GameEventDef"], ctx: MatchContext, eval_ctx: "EvalContext", history: "AgentEventHistory"
) -> list["GameEventDef"]:
    """README 1.4.2 的粗筛全集：地点 / 时间 / 谓词 / 冷却 / 次数 / 互斥。
    后三项是硬过滤，不能降级成权重乘子——冷却期内的事件必须彻底不出现。"""
    blocked_tags = history.active_exclusive_tags(ctx.now)
    out = []
    for e in pool:
        if e.is_draft:
            continue
        if e.weight <= 0:
            # weight<=0 是"只能被 chain 触发，永不参与随机抽取"的约定（如
            # GOLDEN_FISH_REVEAL 只该由 ChainEvent 点名执行）。留在候选池里会在
            # 冷却期把其它候选清空后单独留下，导致 reweight_and_pick 总权重为 0。
            continue
        if not (ctx.location_type in e.applicable_locations or "*" in e.applicable_locations):
            continue
        if e.applicable_time is not None and ctx.time_shichen not in e.applicable_time:
            continue
        if history.in_cooldown(e.event_id, ctx.now, e.cooldown_shichen):
            continue
        if e.max_trigger_per_agent is not None and history.trigger_count(e.event_id) >= e.max_trigger_per_agent:
            continue
        if blocked_tags & set(e.exclusive_tags):
            continue
        if e.predicate is not None and not e.predicate.evaluate(eval_ctx):
            continue
        out.append(e)
    return out


def novelty_weight(event_def: "GameEventDef", history: "AgentEventHistory") -> float:
    """1.4.3：短期记忆衰减 × 标签配额 × 长尾保护，三个乘子相乘。"""
    recency = history.recency_factor(event_def.event_id, curve=event_def.novelty_curve_override)
    tag_quota = history.tag_quota_factor(event_def.tags)
    rarity_bonus = 1.5 if history.trigger_count(event_def.event_id) == 0 else 1.0
    return recency * tag_quota * rarity_bonus


def reweight_and_pick(
    candidates: list["GameEventDef"],
    history: "AgentEventHistory",
    rng: random.Random,
    extra_weight: "Callable[[GameEventDef], float] | None" = None,
) -> "GameEventDef | None":
    """extra_weight 是内容侧临时加权的口子（如 GAME_DESIGN §4.2 灵气潮汐日"妖兽类
    事件权重 ×2"），不改新颖度乘子本身——潮汐加成与"这条事件最近有没有抽过"是两回事。"""
    if not candidates:
        return None
    weights = [c.weight * novelty_weight(c, history) * (extra_weight(c) if extra_weight else 1.0) for c in candidates]
    if sum(weights) <= 0:
        # 防御性兜底：novelty 乘子理论上不会把正权重砸成 0（floor 参数保证下限>0），
        # 但 extra_weight 是外部注入的任意函数，没法保证——总权重非正时 random.choices
        # 会抛异常，这里退化成"抽空"而不是让整回合崩掉。
        return None
    return rng.choices(candidates, weights=weights, k=1)[0]


def tidal_beast_weight_multiplier(event_def: "GameEventDef", now: "GameTime", boosted_tag: str = "妖兽", multiplier: float = 2.0):
    """GAME_DESIGN §4.2："狂暴期"妖兽类事件权重 ×2。用作 reweight_and_pick 的
    extra_weight 参数：`lambda e: tidal_beast_weight_multiplier(e, now)`。"""
    from model.domain.time import GameCalendar

    if GameCalendar.is_tidal_day(now) and boosted_tag in event_def.tags:
        return multiplier
    return 1.0


def pick_variant(defn: "GameEventDef", history: "AgentEventHistory", rng: random.Random) -> int:
    """README 1.4.3 文案变体：同一 eventId 命中时优先未用过 / 最久未用的一条。
    别再让 Occurrence 的 chosen_variant_index 恒为 0。"""
    if len(defn.variants) <= 1:
        return 0
    last = history.last_variant(defn.event_id)
    pool = [i for i in range(len(defn.variants)) if i != last] or list(range(len(defn.variants)))
    return rng.choices(pool, weights=[defn.variants[i].weight for i in pool], k=1)[0]
