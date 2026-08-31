"""view/location_panel_view.py — 位置/地图面板（GAME_DESIGN §2.5）。

只读展示：当前地点名 + 地点类型 + 灵气浓度五格条。不放"可去地点"跳转列表——
移动同样靠聊天（「去酒楼」），面板只做只读展示，维持单一输入入口。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from model.domain.map import WorldView

_ICON_SLOTS = 5
_QI_FULL_SCALE = 1.0  # 灵气浓度基线约 0.3~0.9，潮汐日可能临时超过 1.0，展示时封顶


@dataclass
class LocationPanel:
    location_id: str
    name: str
    location_type: str
    qi_density_icons: str
    weather: str


def _qi_icons(qi_density: float) -> str:
    filled = max(0, min(_ICON_SLOTS, round(qi_density / _QI_FULL_SCALE * _ICON_SLOTS)))
    return "●" * filled + "○" * (_ICON_SLOTS - filled)


def build_location_panel(location_id: str, world: "WorldView") -> LocationPanel:
    return LocationPanel(
        location_id=location_id,
        name=world.name_of(location_id),
        location_type=world.location_type_of(location_id),
        qi_density_icons=_qi_icons(world.qi_density_of(location_id)),
        weather=world.weather(),
    )
