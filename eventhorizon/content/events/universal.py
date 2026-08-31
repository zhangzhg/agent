"""content/events/universal.py — 通用事件（applicable_locations=["*"]，
GAME_DESIGN §9.1 通用生活基础事件）。
"""
from __future__ import annotations

from model.domain.events import EventVariant, GameEventDef
from model.domain.results import StateChange

TIDAL_OMEN = GameEventDef(
    event_id="tidal_omen",
    applicable_locations=("*",),
    applicable_time=None,
    predicate=None,
    weight=1.0,
    duration_shichen=0,
    cooldown_shichen=12,
    max_trigger_per_agent=None,
    exclusive_tags=(),
    priority=5,
    tags=("环境",),
    aliases=(),
    result_pool=(),
    variants=(
        EventVariant("今日恰逢灵气潮汐，四野灵气涌动，修炼者们大多闭门不出。"),
        EventVariant("月色如水，空气中的灵气比往日浓郁了几分。"),
    ),
    is_command=False,
    is_draft=False,
)

SUDDEN_INSIGHT = GameEventDef(
    event_id="sudden_insight",
    applicable_locations=("*",),
    applicable_time=None,
    predicate=None,
    weight=0.5,
    duration_shichen=0,
    cooldown_shichen=48,
    max_trigger_per_agent=None,
    exclusive_tags=(),
    priority=5,
    tags=("修炼", "奇遇"),
    aliases=(),
    # 悟性高的 Agent 顿悟事件恢复更快（GAME_DESIGN §7.5），novelty_curve_override
    # 覆盖默认新鲜度曲线的半衰期；具体系数由录入时按 Agent.insight 分档配置。
    novelty_curve_override={"half_life_steps": 4, "floor": 0.3},
    result_pool=(StateChange(field="cultivation", delta=10), StateChange(field="heart_demon", delta=-0.02)),
    variants=(EventVariant("行走间灵光一闪，你对某处功法关窍忽有所悟。"),),
    is_command=False,
    is_draft=False,
)

WEATHER_SHIFT = GameEventDef(
    event_id="weather_shift",
    applicable_locations=("*",),
    applicable_time=None,
    predicate=None,
    weight=1.0,
    duration_shichen=0,
    cooldown_shichen=12,
    max_trigger_per_agent=None,
    exclusive_tags=(),
    priority=5,
    tags=("环境",),
    aliases=(),
    result_pool=(),
    variants=(EventVariant("天色渐渐变了，一场雨说来就来。"), EventVariant("云开雾散，日头难得地暖和起来。")),
    is_command=False,
    is_draft=False,
)

ALL = (TIDAL_OMEN, SUDDEN_INSIGHT, WEATHER_SHIFT)
