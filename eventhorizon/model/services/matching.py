"""model/services/matching.py — 两阶段匹配 + 新鲜感机制（对应 README 1.4.2 / 1.4.3）。

reweight_and_pick 只做规则新颖度；V2 的向量新颖度以同一函数签名的装饰器/包装形式
叠加一个相似度乘子，不改这个函数本身（1.4.3"是同一步的两个乘子，不是两套系统"）。

predicate_text 分支（用户显式要求：事件"触发条件"允许写成自然语言，用向量相似度
判定代替结构化谓词比较）是对 README 1.4.1"向量补盲区、不替代规则"定位的一次有意识
偏离——预计算好的 predicate_embedding 只在 predicate 为空时才参与判定，e.predicate
仍然是精确判定的硬条件（money_gte 这类不能模糊），两者不冲突。"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from model.domain.agent import AgentEventHistory
    from model.domain.cause import CauseLink
    from model.domain.events import GameEventDef
    from model.domain.predicates import EvalContext
    from model.domain.time import GameTime
    from model.services.ports import EmbeddingPort

# predicate_text 判定的相似度阈值——凭经验给的起始值，没有实测数据支撑，接入真实
# embedding 模型后应该按实际相似度分布重新标定（见 tests/model/services/test_matching.py
# 里几个向量判定用例的取值范围）。
PREDICATE_SIMILARITY_THRESHOLD = 0.75


def build_context_embedding(
    embedding: "EmbeddingPort | None", *, location_type: str, realm: str, money: int, age: int
) -> tuple[float, ...]:
    """给 MatchContext.context_embedding 用：把当前情境的结构化字段拼成一句简短
    文本再编码（README 1.4.1："状态上下文优先读结构化字段…避免每次把整段状态拼
    进去再 embedding"，这里就是那个"结构化字段"版本，不是把叙事原文整段丢进去）。
    embedding 为 None（向量模块关闭）或调用失败（网络/超时——这是活跃对局路径里
    唯一一处会打外部网络的地方，绝不能让它崩掉整个回合）都返回空元组，
    coarse_filter 见到空的 context_embedding 会 fail-open。"""
    if embedding is None:
        return ()
    text = f"地点类型:{location_type} 境界:{realm} 金钱:{money} 年龄:{age}"
    try:
        return tuple(embedding.embed(text))
    except Exception:
        return ()


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
    context_embedding: tuple[float, ...] = field(default_factory=tuple)
    # 当前情境的向量表示，调用方（PlayTurnService 等）在这一回合开始时用 EmbeddingPort
    # 算一次、传进来复用，不在这里每个候选事件各编码一次——README 1.4.1："状态上下文
    # 优先读结构化字段…避免每次把整段状态拼进去再 embedding"。留空 = 向量模块关闭
    # 或者本回合没算（fail-open，predicate_text 分支视为无条件，见 coarse_filter）。


def cosine_similarity(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def coarse_filter(
    pool: list["GameEventDef"],
    ctx: MatchContext,
    eval_ctx: "EvalContext",
    history: "AgentEventHistory",
    similarity_threshold: float = PREDICATE_SIMILARITY_THRESHOLD,
) -> list["GameEventDef"]:
    """README 1.4.2 的粗筛全集：地点 / 时间 / 谓词 / 冷却 / 次数 / 互斥。
    后三项是硬过滤，不能降级成权重乘子——冷却期内的事件必须彻底不出现。

    谓词判定分两种：e.predicate 非空时走精确判定（不变）；e.predicate 为空但
    e.predicate_text 非空时走向量相似度判定——两边（事件的 predicate_embedding、
    本回合的 ctx.context_embedding）都要有向量才能判，缺一边就是"向量模块关闭/
    本回合没算"，fail-open 当无条件处理，不当"永远不满足"（否则写了自然语言条件
    的草稿在没配置向量服务时会变成打不出来的死内容，比没有这个功能还糟）。"""
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
        if e.predicate is not None:
            if not e.predicate.evaluate(eval_ctx):
                continue
        elif e.predicate_text and e.predicate_embedding and ctx.context_embedding:
            if cosine_similarity(e.predicate_embedding, ctx.context_embedding) < similarity_threshold:
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
