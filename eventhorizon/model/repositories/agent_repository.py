"""model/repositories/agent_repository.py — Agent 的读/写立面（对应 README 5.2）。

单机、单存档、单主角（README 1.1 产品边界）：Agent 持久化不另开一张 CRUD 表，
落在全局快照 + 增量日志基础设施上——load() = 最近快照 + 重放 applied_diff，
与"实时对局与读档重放调用同一份 apply 函数"的约束一致（domain/diff.py）。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from model.domain.diff import apply_agent_diff
from model.repositories.codec import agent_from_dict, agent_to_dict

if TYPE_CHECKING:
    from model.domain.agent import Agent
    from model.services.ports import EventLogStore, SnapshotStore


class SqliteAgentRepository:
    """load() = 最近快照 + 重放 applied_diff；save() 写一条新的全量快照（MVP 简化：
    不做脏标记式增量落盘，正确性优先，性能问题留给 §11 TODO#4 一并解决）。"""

    def __init__(self, snapshots: "SnapshotStore", log: "EventLogStore") -> None:
        self._snapshots = snapshots
        self._log = log

    def load(self, agent_id: str) -> "Agent":
        latest = self._snapshots.load_latest_snapshot()
        if latest is None:
            raise LookupError(f"no snapshot found for agent {agent_id!r}; seed one via save() first")
        payload, at = latest
        agent_dict = payload.get("agents", {}).get(agent_id)
        if agent_dict is None:
            raise LookupError(f"agent {agent_id!r} not present in latest snapshot")
        agent = agent_from_dict(agent_dict)
        for occ in self._log.replay_since(at):
            if occ.agent_id != agent_id or occ.applied_diff is None:
                continue
            apply_agent_diff(agent, occ.applied_diff)
        return agent

    def save(self, agent: "Agent") -> None:
        latest = self._snapshots.load_latest_snapshot()
        payload = dict(latest[0]) if latest else {}
        payload.setdefault("agents", {})[agent.agent_id] = agent_to_dict(agent)
        self._snapshots.save_snapshot(payload, agent.time_anchor.current_game_time)
