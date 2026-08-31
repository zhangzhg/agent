"""model/repositories/world_repository.py — 组装只读 WorldView（对应 README 5.2）。

不把可写 WorldState 泄漏到 controller：assemble_view() 只返回 WorldView，真正的
可写引用只在 pipeline.ApplyDiffStep 里通过 WorldView.mutable_state() 拿到。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from model.domain.map import WorldState, WorldView
from model.repositories.codec import world_state_from_dict, world_state_to_dict

if TYPE_CHECKING:
    from model.services.ports import SnapshotStore


class SqliteWorldRepository:
    """世界状态与 Agent 共用同一份全局快照 blob（"world" 键），保持"全局快照"是一份
    整体（README 1.8），不是两张互不相干的表。"""

    def __init__(self, snapshots: "SnapshotStore") -> None:
        self._snapshots = snapshots
        self._state: WorldState | None = None

    def _load_or_init(self) -> WorldState:
        if self._state is not None:
            return self._state
        latest = self._snapshots.load_latest_snapshot()
        if latest is not None and "world" in latest[0]:
            self._state = world_state_from_dict(latest[0]["world"])
        else:
            self._state = WorldState()
        return self._state

    def assemble_view(self) -> WorldView:
        return WorldView(_state=self._load_or_init())

    def save(self, at) -> None:
        state = self._load_or_init()
        latest = self._snapshots.load_latest_snapshot()
        payload = dict(latest[0]) if latest else {}
        payload["world"] = world_state_to_dict(state)
        self._snapshots.save_snapshot(payload, at)


class InMemoryWorldRepository:
    """测试/单机会话用：直接持有一个 WorldState，不经快照往返。"""

    def __init__(self, state: WorldState | None = None) -> None:
        self._state = state or WorldState()

    def assemble_view(self) -> WorldView:
        return WorldView(_state=self._state)

    def save(self, at) -> None:
        pass  # 状态已经活在同一个共享 WorldState 对象上，没有独立的落盘步骤要做
