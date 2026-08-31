"""model/repositories/sqlite_event_repository.py — SQLite 持久化（对应 README 5.2）。"""
from __future__ import annotations

import json
import sqlite3

from model.domain.events import GameEventDef
from model.repositories.codec import event_def_from_dict, event_def_to_dict


def _deserialize(payload: str) -> GameEventDef:
    return event_def_from_dict(json.loads(payload))


def _serialize(event: GameEventDef) -> str:
    return json.dumps(event_def_to_dict(event), ensure_ascii=False)


class SqliteEventRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS event_defs (
                event_id TEXT PRIMARY KEY,
                is_draft INTEGER NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def get_by_id(self, event_id: str) -> GameEventDef | None:
        row = self._conn.execute("SELECT payload FROM event_defs WHERE event_id = ?", (event_id,)).fetchone()
        return _deserialize(row[0]) if row else None

    def load_event_defs(self, location_type: str | None = None) -> list[GameEventDef]:
        # MVP：拉全部已发布，在内存按 location_type 过滤，避免 json_each 绑死存储格式
        rows = self._conn.execute("SELECT payload FROM event_defs WHERE is_draft = 0")
        defs = [_deserialize(r[0]) for r in rows]
        if location_type is None:
            return defs
        return [e for e in defs if location_type in e.applicable_locations or "*" in e.applicable_locations]

    def save_event_def(self, event: GameEventDef) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO event_defs (event_id, is_draft, payload) VALUES (?, ?, ?)",
            (event.event_id, int(event.is_draft), _serialize(event)),
        )
        self._conn.commit()

    def delete_event_def(self, event_id: str) -> bool:
        cur = self._conn.execute("DELETE FROM event_defs WHERE event_id = ?", (event_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def list_all(self) -> list[GameEventDef]:
        """草稿 + 已发布，全部返回——只供录入编辑器的事件列表用；对局路径必须走
        load_event_defs()，它会把草稿过滤掉（README 1.3.3："草稿不进入粗筛的合格池"）。"""
        rows = self._conn.execute("SELECT payload FROM event_defs")
        return [_deserialize(r[0]) for r in rows]


class InMemoryEventRepository:
    """测试/编辑器沙盒用：不落盘，语义与 SqliteEventRepository 一致。"""

    def __init__(self, events: dict[str, GameEventDef] | None = None) -> None:
        self._events: dict[str, GameEventDef] = dict(events or {})

    def get_by_id(self, event_id: str) -> GameEventDef | None:
        return self._events.get(event_id)

    def load_event_defs(self, location_type: str | None = None) -> list[GameEventDef]:
        defs = [e for e in self._events.values() if not e.is_draft]
        if location_type is None:
            return defs
        return [e for e in defs if location_type in e.applicable_locations or "*" in e.applicable_locations]

    def save_event_def(self, event: GameEventDef) -> None:
        self._events[event.event_id] = event

    def delete_event_def(self, event_id: str) -> bool:
        return self._events.pop(event_id, None) is not None

    def list_all(self) -> list[GameEventDef]:
        return list(self._events.values())
