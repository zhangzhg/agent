"""model/services/retreat_intent_parser.py — 闭关时长的自然语言解析（GAME_DESIGN
§4.3）。

"十年" → 固定时辰目标；"到金丹为止" → 目标境界（RetreatService.run 用 stop_when
判定，target_shichen 仍是安全上限，防止一直卡在同一境界怎么也过不去）；
"随便" → 按当前境界剩余修为估算一个建议游戏年数，标记为需要二次确认。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from model.domain.time import DAYS_PER_MONTH, MONTHS_PER_YEAR, SHICHEN_PER_DAY

if TYPE_CHECKING:
    from model.domain.agent import Agent
    from model.domain.balance import BalanceTable

SHICHEN_PER_YEAR = SHICHEN_PER_DAY * DAYS_PER_MONTH * MONTHS_PER_YEAR
_SAFETY_CAP_YEARS = 500  # "到XX为止"式闭关的安全上限，避免资质太低时无限循环

_ARABIC_YEAR_PATTERN = re.compile(r"(\d+)\s*年")
_CHINESE_YEAR_PATTERN = re.compile(r"^([一二两三四五六七八九十百]+)年$")
_UNTIL_PATTERN = re.compile(r"到\s*(.+?)\s*(?:境界)?为止")
_RANDOM_PHRASES = ("随便", "随意", "都行", "你看着办")

_CHINESE_DIGITS = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def _parse_chinese_number(s: str) -> int | None:
    """支持"十""二十""三十五""一百"这类常见闭关口语数字，不追求完整中文数词文法。"""
    if not s:
        return None
    if s == "十":
        return 10
    if s.endswith("百"):
        prefix = s[:-1]
        base = _CHINESE_DIGITS.get(prefix, 1) if prefix else 1
        return base * 100
    if "十" in s:
        left, _, right = s.partition("十")
        tens = _CHINESE_DIGITS.get(left, 1) if left else 1
        ones = _CHINESE_DIGITS.get(right, 0) if right else 0
        return tens * 10 + ones
    return _CHINESE_DIGITS.get(s)


def _extract_years(text: str) -> int | None:
    m = _ARABIC_YEAR_PATTERN.search(text)
    if m:
        return int(m.group(1))
    m2 = _CHINESE_YEAR_PATTERN.match(text)
    if m2:
        return _parse_chinese_number(m2.group(1))
    return None


def _suggest_years(agent: "Agent", balance: "BalanceTable") -> int:
    """"随便"时给的默认建议：按当前境界剩余修为 / 修炼速率估算游戏年数。"""
    required = balance.cultivation_required_for(agent.realm)
    if required is None:
        return 10
    remaining = max(0.0, required - agent.cultivation)
    cfg = balance.cultivation_rate
    rate = cfg["base_per_shichen"] * cfg["qi_density_weight"] * max(agent.aptitude, 0.1)
    if rate <= 0:
        return 10
    shichen_needed = remaining / rate
    return max(1, round(shichen_needed / SHICHEN_PER_YEAR))


@dataclass
class RetreatPlan:
    target_shichen: int  # 安全上限；固定时长模式下就是精确目标
    stop_at_realm: str | None = None  # 达到该境界即提前结束
    is_default_suggestion: bool = False  # "随便"给出的建议值，需要二次确认
    description: str = ""


def parse_retreat_duration(text: str, agent: "Agent", balance: "BalanceTable") -> RetreatPlan | None:
    """解析失败返回 None（PlayTurnService 据此回问"没听懂要闭关多久"）。"""
    stripped = text.strip()
    if not stripped:
        return None

    until_match = _UNTIL_PATTERN.search(stripped)
    if until_match:
        realm = until_match.group(1).strip()
        if realm not in balance.realm_order:
            return None
        return RetreatPlan(
            target_shichen=_SAFETY_CAP_YEARS * SHICHEN_PER_YEAR, stop_at_realm=realm, description=f"到{realm}为止"
        )

    if any(phrase in stripped for phrase in _RANDOM_PHRASES):
        years = _suggest_years(agent, balance)
        return RetreatPlan(
            target_shichen=years * SHICHEN_PER_YEAR, is_default_suggestion=True, description=f"建议闭关 {years} 年"
        )

    years = _extract_years(stripped)
    if years is None or years <= 0:
        return None
    return RetreatPlan(target_shichen=years * SHICHEN_PER_YEAR, description=f"{years}年")


def stop_when_realm_reached(target_realm: str) -> "Callable[[Agent], bool]":
    def _predicate(agent: "Agent") -> bool:
        return agent.realm == target_realm

    return _predicate
