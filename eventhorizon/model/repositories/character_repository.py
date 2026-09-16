"""model/repositories/character_repository.py — 玩家人物身份与事件快照墙钟。

NPC 不进这张表。验证码只存 sha256，明文只在建角时返回一次。
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CharacterRecord:
    agent_id: str
    verify_code_hash: str
    created_at: float
    event_saved_at: float


class CharacterExistsError(ValueError):
    pass


class SqliteCharacterRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS player_characters (
                agent_id TEXT PRIMARY KEY,
                verify_code_hash TEXT NOT NULL,
                created_at REAL NOT NULL,
                event_saved_at REAL NOT NULL
            )
            """
        )
        self._conn.commit()

    def create(self, record: CharacterRecord) -> None:
        try:
            self._conn.execute(
                "INSERT INTO player_characters (agent_id, verify_code_hash, created_at, event_saved_at) "
                "VALUES (?, ?, ?, ?)",
                (record.agent_id, record.verify_code_hash, record.created_at, record.event_saved_at),
            )
        except sqlite3.IntegrityError as exc:
            raise CharacterExistsError(record.agent_id) from exc
        self._conn.commit()

    def get(self, agent_id: str) -> CharacterRecord | None:
        row = self._conn.execute(
            "SELECT agent_id, verify_code_hash, created_at, event_saved_at "
            "FROM player_characters WHERE agent_id = ?",
            (agent_id,),
        ).fetchone()
        if row is None:
            return None
        return CharacterRecord(*row)

    def touch_event_saved_at(self, agent_id: str, saved_at: float) -> None:
        self._conn.execute(
            "UPDATE player_characters SET event_saved_at = ? WHERE agent_id = ?",
            (saved_at, agent_id),
        )
        self._conn.commit()


class InMemoryCharacterRepository:
    def __init__(self) -> None:
        self._rows: dict[str, CharacterRecord] = {}

    def create(self, record: CharacterRecord) -> None:
        if record.agent_id in self._rows:
            raise CharacterExistsError(record.agent_id)
        self._rows[record.agent_id] = record

    def get(self, agent_id: str) -> CharacterRecord | None:
        return self._rows.get(agent_id)

    def touch_event_saved_at(self, agent_id: str, saved_at: float) -> None:
        current = self._rows.get(agent_id)
        if current is None:
            return
        self._rows[agent_id] = CharacterRecord(
            current.agent_id, current.verify_code_hash, current.created_at, saved_at
        )
