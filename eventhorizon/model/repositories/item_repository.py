"""model/repositories/item_repository.py — 物品定义仓库（GAME_DESIGN §2.6）。

最小实现：内存字典 + 可选 SQLite 落盘。物品定义随内容包一起分发，不像事件那样
需要草稿/发布两态（物品本身不参与粗筛/抽取，没有"未发布物品污染合格池"的问题）。
"""
from __future__ import annotations

import json
import sqlite3

from model.domain.items import ItemDef, ItemKind


def _item_to_dict(item: ItemDef) -> dict:
    return {
        "item_id": item.item_id,
        "kind": item.kind.value,
        "stackable": item.stackable,
        "unique": item.unique,
        "name": item.name,
        "description": item.description,
    }


def _item_from_dict(d: dict) -> ItemDef:
    return ItemDef(
        item_id=d["item_id"],
        kind=ItemKind(d["kind"]),
        stackable=d.get("stackable", True),
        unique=d.get("unique", False),
        name=d.get("name", ""),
        description=d.get("description", ""),
    )


class InMemoryItemRepository:
    def __init__(self, items: dict[str, ItemDef] | None = None) -> None:
        self._items: dict[str, ItemDef] = dict(items or {})

    def get_by_id(self, item_id: str) -> ItemDef | None:
        return self._items.get(item_id)

    def save_item_def(self, item: ItemDef) -> None:
        self._items[item.item_id] = item

    def delete_item_def(self, item_id: str) -> bool:
        return self._items.pop(item_id, None) is not None

    def list_all(self) -> list[ItemDef]:
        return list(self._items.values())

    def all_ids(self) -> set[str]:
        return set(self._items.keys())


class SqliteItemRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self._conn.execute("CREATE TABLE IF NOT EXISTS item_defs (item_id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
        self._conn.commit()

    def get_by_id(self, item_id: str) -> ItemDef | None:
        row = self._conn.execute("SELECT payload FROM item_defs WHERE item_id = ?", (item_id,)).fetchone()
        return _item_from_dict(json.loads(row[0])) if row else None

    def save_item_def(self, item: ItemDef) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO item_defs (item_id, payload) VALUES (?, ?)",
            (item.item_id, json.dumps(_item_to_dict(item), ensure_ascii=False)),
        )
        self._conn.commit()

    def delete_item_def(self, item_id: str) -> bool:
        cur = self._conn.execute("DELETE FROM item_defs WHERE item_id = ?", (item_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def list_all(self) -> list[ItemDef]:
        rows = self._conn.execute("SELECT payload FROM item_defs")
        return [_item_from_dict(json.loads(r[0])) for r in rows]
