"""model/repositories/embedding/sqlite_vector_index.py — V2 向量索引（对应 README
1.4.1）。

优先 SQLite 存事件元数据；向量索引 V2 再接入。事件 embedding 在录入时预计算并
缓存，不在触发时现场编码全库——这里只做"存 + 余弦相似度检索"的轻量实现，重活
（近似最近邻）留给真正接入外部库时替换。
"""
from __future__ import annotations

import json
import math
import sqlite3


class SqliteVectorIndex:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS event_embeddings (event_id TEXT PRIMARY KEY, vector TEXT NOT NULL)"
        )
        self._conn.commit()

    def upsert(self, event_id: str, vector: list[float]) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO event_embeddings (event_id, vector) VALUES (?, ?)",
            (event_id, json.dumps(vector)),
        )
        self._conn.commit()

    def most_similar(self, vector: list[float], top_k: int = 5, exclude_event_id: str | None = None) -> list[tuple[str, float]]:
        rows = self._conn.execute("SELECT event_id, vector FROM event_embeddings")
        scored = []
        for event_id, raw in rows:
            if event_id == exclude_event_id:
                continue
            candidate = json.loads(raw)
            scored.append((event_id, _cosine_similarity(vector, candidate)))
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:top_k]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
