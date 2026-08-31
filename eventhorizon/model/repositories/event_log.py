"""model/repositories/event_log.py — Event Sourcing 增量日志（对应 README 1.8 /
5.2）。

命令段与奇遇段各写一条 Occurrence，JSON 必须含 applied_diff；改动了地点属性的
还须含 world_diff，否则快照之后的地图变更重放即丢。缺 applied_diff 的旧日志视为
损坏，跳过并告警。
"""
from __future__ import annotations

import json
import logging
import sqlite3

from model.domain.events import GameEventOccurrence
from model.repositories.codec import occurrence_from_dict, occurrence_to_dict

_logger = logging.getLogger("eventhorizon.event_log")


class SqliteEventLogStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS event_log (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                ordinal INTEGER NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def append(self, occurrence: GameEventOccurrence) -> None:
        # applied_diff 缺失说明这条事件被 rejected 就不该走到这里；仍兜底跳过，不写坏档
        if occurrence.applied_diff is None:
            _logger.warning("refusing to log occurrence without applied_diff: %r", occurrence.event_id)
            return
        payload = json.dumps(occurrence_to_dict(occurrence), ensure_ascii=False)
        ordinal = occurrence.occurred_at._ordinal() if hasattr(occurrence.occurred_at, "_ordinal") else 0
        self._conn.execute("INSERT INTO event_log (ordinal, payload) VALUES (?, ?)", (ordinal, payload))
        self._conn.commit()

    def replay_since(self, since) -> list[GameEventOccurrence]:
        # 严格大于：`since` 是快照拍下时的时刻，那一刻及之前发生的一切已经烤进了
        # 快照本身。用 >= 会把恰好卡在快照时刻上的日志条目（duration_shichen=0
        # 的事件很常见，时钟压根没往前挪）在下一次 load() 时重放一遍，等于把同一条
        # diff 应用了两次——这曾经是真实存在的复读 bug。
        since_ordinal = since._ordinal() if hasattr(since, "_ordinal") else 0
        rows = self._conn.execute(
            "SELECT payload FROM event_log WHERE ordinal > ? ORDER BY seq ASC", (since_ordinal,)
        )
        out: list[GameEventOccurrence] = []
        for (payload,) in rows:
            record = json.loads(payload)
            if record.get("applied_diff") is None:
                _logger.warning("skipping corrupt log entry without applied_diff: %r", record.get("event_id"))
                continue
            out.append(occurrence_from_dict(record))
        return out


class InMemoryEventLogStore:
    """测试用：语义与 SqliteEventLogStore 一致，不落盘。"""

    def __init__(self) -> None:
        self._entries: list[GameEventOccurrence] = []

    def append(self, occurrence: GameEventOccurrence) -> None:
        if occurrence.applied_diff is None:
            _logger.warning("refusing to log occurrence without applied_diff: %r", occurrence.event_id)
            return
        self._entries.append(occurrence)

    def replay_since(self, since) -> list[GameEventOccurrence]:
        # 严格大于，理由见 SqliteEventLogStore.replay_since 的注释。
        return [occ for occ in self._entries if since < occ.occurred_at]
