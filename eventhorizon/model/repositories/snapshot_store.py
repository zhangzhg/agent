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


# 只保留最近这么多份快照。load_latest_snapshot() 永远只读最新一行
# （ORDER BY seq DESC LIMIT 1，全项目没有第二个读快照的地方），更早的行纯粹是
# 历史存档，对正确性没有贡献；而每回合会写 1~2 份**全量** payload（世界 ~4KB +
# 全部 Agent），不清理的话一局长对话就能滚出几十 MB。留一小段窗口是为了出事时
# 还能人工翻一眼前几步的状态，不是给程序读的。
_SNAPSHOT_RETENTION = 20


class SqliteSnapshotStore:
    def __init__(self, conn: sqlite3.Connection, retention: int = _SNAPSHOT_RETENTION) -> None:
        self._conn = conn
        self._retention = max(1, retention)
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
        # 跟 INSERT 同一个事务里裁剪，避免"插入成功、清理失败"留下无界增长。
        # 按 seq 而不是 at 取舍：at 是游戏内时刻，duration_shichen=0 的事件不会让它
        # 前进，同一时刻可能对应多行；seq 是写入顺序，永远单调。
        # 严格小于：子查询取的是"第 retention 新"那一行的 seq，它本身要留下，
        # 只删比它更旧的。用 <= 会把它也删掉，retention=1 时甚至会把刚插入的那行
        # 删掉、快照表直接清空（测试 test_retention_of_one_keeps_working 盯着这个）。
        self._conn.execute(
            "DELETE FROM snapshots WHERE seq < ("
            "  SELECT seq FROM snapshots ORDER BY seq DESC LIMIT 1 OFFSET ?"
            ")",
            (self._retention - 1,),
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
