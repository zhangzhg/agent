"""model/services/registry.py — EventRegistry（工厂模式，对应 README 3.4）。

两套键：总线系统事件用 type=TimePassEvent|MapUpdateEvent|DeathEvent|
GameEventOccurrence；库内玩法用 event_id 从 EventRepository 取 GameEventDef，
不要为 eat/meditate 各注册一个 type。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from model.services.handlers.game_event_handler import EventHandler


@dataclass
class RegistryEntry:
    factory: Callable[[dict], object]
    handler: "EventHandler | None"
    priority: int = 0
    schema_version: int = 1


class EventRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, RegistryEntry] = {}

    def register(self, type_key: str, entry: RegistryEntry) -> None:
        self._entries[type_key] = entry

    def get(self, type_key: str) -> RegistryEntry | None:
        return self._entries.get(type_key)

    def create(self, record: dict) -> object | None:
        """两套键：总线系统事件用 type=…；库内玩法用 event_id 从 EventRepository 取
        GameEventDef，不要为 eat/meditate 各注册一个 type。"""
        entry = self._entries.get(record.get("type"))
        if entry is None:
            _log_unknown_type(record.get("type"))
            return None
        return entry.factory(_migrate(record, entry.schema_version))


def _migrate(record: dict, target_version: int) -> dict:
    """旧存档字段缺失时在这里填默认值，不在业务 Handler 里做兼容分支。"""
    migrated = dict(record)
    migrated.setdefault("schema_version", target_version)
    return migrated


def _log_unknown_type(type_key: str | None) -> None:
    """未知 type 跳过并记警告，不让整档失败（README 3.4）。"""
    import logging

    logging.getLogger("eventhorizon.registry").warning("unknown event type on replay: %r", type_key)
