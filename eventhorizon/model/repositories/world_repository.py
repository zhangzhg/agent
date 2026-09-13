"""model/repositories/world_repository.py — 组装只读 WorldView（对应 README 5.2）。

不把可写 WorldState 泄漏到 controller：assemble_view() 只返回 WorldView，真正的
可写引用只在 pipeline.ApplyDiffStep 里通过 WorldView.mutable_state() 拿到。
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from model.domain.map import WorldState, WorldView
from model.repositories.codec import world_state_from_dict, world_state_to_dict

if TYPE_CHECKING:
    from model.services.ports import SnapshotStore


def _serialize(world_json: dict) -> str:
    """脏判定用的稳定序列化——sort_keys 保证同样的世界状态永远得到同一个字符串，
    不受 dict 插入顺序影响（否则新增一个地点再删掉，就可能因为键序变了被误判成脏）。"""
    return json.dumps(world_json, ensure_ascii=False, sort_keys=True)


class SqliteWorldRepository:
    """世界状态与 Agent 共用同一份全局快照 blob（"world" 键），保持"全局快照"是一份
    整体（README 1.8），不是两张互不相干的表。"""

    def __init__(self, snapshots: "SnapshotStore") -> None:
        self._snapshots = snapshots
        self._state: WorldState | None = None
        self._last_saved: str | None = None  # 上次真正写盘的 world 序列化结果，见 save()

    def _load_or_init(self) -> WorldState:
        if self._state is not None:
            return self._state
        latest = self._snapshots.load_latest_snapshot()
        if latest is not None and "world" in latest[0]:
            self._state = world_state_from_dict(latest[0]["world"])
            self._last_saved = _serialize(latest[0]["world"])
        else:
            self._state = WorldState()
        return self._state

    def assemble_view(self) -> WorldView:
        return WorldView(_state=self._load_or_init())

    def save(self, at) -> None:
        """世界没变就不写盘。ChatController 每回合无条件调这个，但绝大多数回合
        世界压根没动（只有移动创作出新地点、神识扫描翻出隐藏点位这类才会变），
        而每写一次就是一整份 payload（世界 ~4KB + 快照里带着的全部 Agent）新增
        一行。比对序列化结果虽然要序列化一次，但省掉的是磁盘写入和无界增长的
        行数，这笔买卖划算得多。

        跳过写入是安全的：agent_repository.save() 每次都会把 latest payload 整个
        复制一份再改 agents 键，world 键会被原样带到新行上，不会因为这里没写就
        丢掉。"""
        state = self._load_or_init()
        world_json = world_state_to_dict(state)
        serialized = _serialize(world_json)
        if serialized == self._last_saved:
            return
        latest = self._snapshots.load_latest_snapshot()
        payload = dict(latest[0]) if latest else {}
        payload["world"] = world_json
        self._snapshots.save_snapshot(payload, at)
        self._last_saved = serialized


class InMemoryWorldRepository:
    """测试/单机会话用：直接持有一个 WorldState，不经快照往返。"""

    def __init__(self, state: WorldState | None = None) -> None:
        self._state = state or WorldState()

    def assemble_view(self) -> WorldView:
        return WorldView(_state=self._state)

    def save(self, at) -> None:
        pass  # 状态已经活在同一个共享 WorldState 对象上，没有独立的落盘步骤要做
