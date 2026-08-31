"""model/services/exploration_service.py — 神识扫描等只读探索命令（GAME_DESIGN
§5.3）。

inspect 类只读命令：不消耗回合、不进 AgentEventHistory。命中隐藏点位的概率由地点
的"隐蔽度"属性决定（策划配置，示意 15%~40%）；未命中给一句烘托叙述而非"无事发生"
的冷淡回复。发现状态要落进 WorldState 才能跨会话保留，因此仍然只通过
apply_world_diff 写入，不直接 setattr。
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

from model.domain.diff import LocationAttrChange, WorldDiff, apply_world_diff

if TYPE_CHECKING:
    from model.domain.map import WorldView

_MISS_NARRATIONS = (
    "你运转神识，一时并无异常。",
    "灵识扫过四周，只有寻常草木气息。",
    "凝神细察，未有所获。",
)


@dataclass
class ScanResult:
    found_location_id: str | None
    narrative: str


def scan_for_hidden_locations(current_location_id: str, world: "WorldView", rng: random.Random) -> ScanResult:
    """按每个候选点位各自的隐蔽度独立判定命中；一次扫描最多发现一处。"""
    for loc in world.hidden_candidates_at(current_location_id):
        if rng.random() < loc.concealment:
            diff = WorldDiff(location_changes=(LocationAttrChange(loc.location_id, "discovered", False, True),))
            apply_world_diff(world.mutable_state(), diff)
            return ScanResult(
                found_location_id=loc.location_id,
                narrative=f"你的神识忽有所感——{loc.name}的痕迹一闪而过！",
            )
    return ScanResult(found_location_id=None, narrative=rng.choice(_MISS_NARRATIONS))
