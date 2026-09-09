"""model/repositories/agent_repository.py — Agent 的读/写立面（对应 README 5.2）。

单机、单存档、单主角（README 1.1 产品边界）：Agent 持久化不另开一张 CRUD 表，
落在全局快照 + 增量日志基础设施上——load() = 最近快照 + 重放 applied_diff，
与"实时对局与读档重放调用同一份 apply 函数"的约束一致（domain/diff.py）。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from model.domain.diff import apply_agent_diff
from model.repositories.codec import agent_from_dict, agent_to_dict

if TYPE_CHECKING:
    from model.domain.agent import Agent
    from model.domain.time import GameTime
    from model.services.ports import EventLogStore, SnapshotStore


class SqliteAgentRepository:
    """load() = 最近快照 + 重放 applied_diff；save() 写一条新的全量快照（MVP 简化：
    不做脏标记式增量落盘，正确性优先，性能问题留给 §11 TODO#4 一并解决）。

    快照行的 `at` 必须来自全局时钟（`now_provider`），不能用 `agent.time_anchor.
    current_game_time`：那个字段只在"这个 Agent 刚经历了一次非零时长的行动"之后
    才等于全局当前时刻，单主角场景下这恰好每次都成立，掩盖了问题——一旦第二个
    Agent（NPC）只触发 duration_shichen=0 的事件，它的锚点永远停在出生时刻，之后
    每次 save() 都会把 `at` 记成那个早已过去的时刻，下次 load() 的 replay_since(at)
    就会把它自己从出生以来的全部历史重新应用一遍，diff 越滚越大（曾经是真实
    复现过的 bug：NPC 的修为在几十个时辰内滚到几百）。"""

    def __init__(
        self, snapshots: "SnapshotStore", log: "EventLogStore", now_provider: "Callable[[], GameTime]"
    ) -> None:
        self._snapshots = snapshots
        self._log = log
        self._now_provider = now_provider

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
        self._snapshots.save_snapshot(payload, self._now_provider())

    def list_all(self) -> "list[Agent]":
        """全部 Agent（玩家 + NPC），各自按自己的增量日志重放到当前时刻——不能只
        反序列化快照里的 dict，否则拿到的是"上次存盘那一刻"的旧状态。"""
        latest = self._snapshots.load_latest_snapshot()
        if latest is None:
            return []
        payload, _at = latest
        return [self.load(agent_id) for agent_id in payload.get("agents", {})]
