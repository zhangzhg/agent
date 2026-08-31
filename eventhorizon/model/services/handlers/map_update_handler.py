"""model/services/handlers/map_update_handler.py — 改地点状态（对应 README 3.2）。

world 侧对 Location 使用薄状态（完好/废墟/秘境开启），这里只做属性落地；
onEnter/onExit 式的联动（换事件池标签等）留给读取 Location.condition 的调用方。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from model.domain.diff import WorldDiff, apply_world_diff

if TYPE_CHECKING:
    from model.domain.map import WorldState
    from model.domain.system_events import MapUpdateEvent


class MapUpdateHandler:
    def __init__(self, world: "WorldState") -> None:
        self._world = world

    def handle(self, event: "MapUpdateEvent") -> None:
        apply_world_diff(self._world, WorldDiff(location_changes=event.changes))
