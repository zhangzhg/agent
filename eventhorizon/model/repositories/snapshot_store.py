"""model/repositories/snapshot_store.py — 全局快照（对应 README 1.8 / 5.2）。

每游戏日对 GameClock、所有 Location 节点属性、当前世界环境状态、以及全部 Agent
做全量快照（Agent 快照必须含挂起字段与 AgentEventHistory，见 agent_repository.py
的 build_full_snapshot）。快照记录 balance_version 与 rng_seed：前者保证旧档不被
新数值表改写历史；后者只为调试复现，不参与重放正确性（重放靠 diff，不靠重掷）。
"""
from __future__ import annotations

import json
import sqlite3

from model.repositories.codec import game_time_from_dict, game_time_to_dict


class SqliteSnapshotStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS snapshots (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                at TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def save_snapshot(self, world_state: dict, at) -> None:
        self._conn.execute(
            "INSERT INTO snapshots (at, payload) VALUES (?, ?)",
            (json.dumps(game_time_to_dict(at)), json.dumps(world_state, ensure_ascii=False)),
        )
        self._conn.commit()

    def load_latest_snapshot(self):
        row = self._conn.execute("SELECT at, payload FROM snapshots ORDER BY seq DESC LIMIT 1").fetchone()
        if row is None:
            return None
        at_json, payload = row
        return json.loads(payload), game_time_from_dict(json.loads(at_json))


class InMemorySnapshotStore:
    """测试用：语义与 SqliteSnapshotStore 一致，不落盘。"""

    def __init__(self) -> None:
        self._latest: tuple[dict, object] | None = None

    def save_snapshot(self, world_state: dict, at) -> None:
        self._latest = (world_state, at)

    def load_latest_snapshot(self):
        return self._latest
