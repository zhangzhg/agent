"""view/character_panel_view.py — 角色状态面板（GAME_DESIGN §2.4，数值展示的
克制原则）。

境界显示当前境界 + 修为进度条，条到头不自动突破。寿元不显示具体数字，只显示
模糊态，避免变成焦虑倒计时。心魔/悟性等隐藏属性完全不在面板展示。饱食是纯
装饰化的五格图标，不做成"饿死倒计时"。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from model.domain.agent import Agent
    from model.domain.balance import BalanceTable

_ICON_SLOTS = 5
_LAYER_NAMES = ("一", "二", "三", "四", "五", "六", "七", "八", "九")
_LIFESPAN_CRITICAL_RATIO = 0.15
_LIFESPAN_WORRYING_RATIO = 0.4


@dataclass
class CharacterPanel:
    realm: str
    cultivation_progress_text: str  # 如"练气三层 68/100"
    lifespan_label: str  # 模糊态，永远不是具体数字
    satiety_icons: str  # 如"●●●●○"
    money: int
    inventory_count: int


def _lifespan_label(agent: "Agent", balance: "BalanceTable") -> str:
    cap = balance.lifespan_by_realm.get(agent.realm, 80.0)
    ratio = (agent.lifespan_left / cap) if cap else 0.0
    if ratio <= _LIFESPAN_CRITICAL_RATIO:
        return "大限将近"
    if ratio <= _LIFESPAN_WORRYING_RATIO:
        return "略感体力不济"
    return "年富力强"


def _cultivation_progress_text(agent: "Agent", balance: "BalanceTable") -> str:
    if agent.realm == "练气":
        # 练气不建模为独立的 realm_order 子项（见 balance.py 的说明），层数由
        # cultivation // 100 近似展示，纯粹是显示层的换算，不影响底层数值。
        layer = max(1, min(9, int(agent.cultivation // 100) + 1))
        within = int(agent.cultivation % 100)
        return f"练气{_LAYER_NAMES[layer - 1]}层 {within}/100"
    required = balance.cultivation_required_for(agent.realm)
    if required is None:
        return agent.realm
    return f"{agent.realm} {int(agent.cultivation)}/{int(required)}"


def _satiety_icons(agent: "Agent") -> str:
    filled = max(0, min(_ICON_SLOTS, round(agent.satiety / 100 * _ICON_SLOTS)))
    return "●" * filled + "○" * (_ICON_SLOTS - filled)


def build_character_panel(agent: "Agent", balance: "BalanceTable") -> CharacterPanel:
    return CharacterPanel(
        realm=agent.realm,
        cultivation_progress_text=_cultivation_progress_text(agent, balance),
        lifespan_label=_lifespan_label(agent, balance),
        satiety_icons=_satiety_icons(agent),
        money=agent.money,
        inventory_count=sum(agent.inventory.counts.values()),
    )
