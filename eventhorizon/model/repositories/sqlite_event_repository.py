"""model/repositories/sqlite_event_repository.py — SQLite 持久化（对应 README 5.2）。"""
from __future__ import annotations

import json
import sqlite3

from model.domain.events import LIVE_EVENT_ID_PREFIX, GameEventDef
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

    def published_event_ids(self) -> set[str]:
        """只要 id 集合的场景（联动校验的 ValidationCatalog）专用——不要为了拿一
        把 id 就 load_event_defs(None) 把整个事件库反序列化一遍。实时创作每处理一
        句没听懂的话就要建一次 catalog，而 live_ 事件只增不减，全量反序列化的成本
        会随对局时长线性上涨。"""
        rows = self._conn.execute("SELECT event_id FROM event_defs WHERE is_draft = 0")
        return {r[0] for r in rows}

    def prune_live_events(self, keep: int, protected_ids: "set[str] | None" = None) -> int:
        """把实时创作的事件（live_ 前缀）总数压回 keep 条以内，删最老的，返回删除
        条数。手工/种子内容一律不碰。

        为什么需要：每一句没被识别的玩家输入都会创作出一条永久事件，只增不减——
        录入编辑器的列表会被玩家碎碎念淹没，向量兜底每回合装载的命令池也越滚越大。

        按 rowid 排序当"最老"：live_ 事件的 id 是随机 uuid，本身没有顺序信息；这些
        事件只在创作时 INSERT 一次、之后不会被 INSERT OR REPLACE 改写，所以 sqlite
        的隐式 rowid 恰好就是创建顺序。

        protected_ids 是"当前还被引用着、删了会留下悬空引用"的 id（挂起的奇遇、
        待结算的延迟结果、流程图宿主事件，见调用方 play_turn.py）——宁可暂时超出
        keep 一点，也不能把玩家正卡在上面的那条事件删掉。"""
        protected = protected_ids or set()
        rows = self._conn.execute(
            "SELECT event_id FROM event_defs WHERE event_id LIKE ? ORDER BY rowid DESC",
            (LIVE_EVENT_ID_PREFIX + "%",),
        ).fetchall()
        live_ids = [r[0] for r in rows]
        # rowid DESC = 从新到旧；跳过前 keep 条（要留的），其余的老货里再排除受保护的。
        doomed = [eid for eid in live_ids[keep:] if eid not in protected]
        if not doomed:
            return 0
        self._conn.executemany("DELETE FROM event_defs WHERE event_id = ?", [(e,) for e in doomed])
        self._conn.commit()
        return len(doomed)

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

    def published_event_ids(self) -> set[str]:
        return {e.event_id for e in self._events.values() if not e.is_draft}

    def prune_live_events(self, keep: int, protected_ids: "set[str] | None" = None) -> int:
        """语义与 SqliteEventRepository 一致：dict 保插入顺序，等价于那边的 rowid。"""
        protected = protected_ids or set()
        live_ids = [e for e in self._events if e.startswith(LIVE_EVENT_ID_PREFIX)]
        doomed = [eid for eid in live_ids[: max(0, len(live_ids) - keep)] if eid not in protected]
        for eid in doomed:
            del self._events[eid]
        return len(doomed)

    def save_event_def(self, event: GameEventDef) -> None:
        self._events[event.event_id] = event

    def delete_event_def(self, event_id: str) -> bool:
        return self._events.pop(event_id, None) is not None

    def list_all(self) -> list[GameEventDef]:
        return list(self._events.values())
