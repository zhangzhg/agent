"""model/services/event_bus.py — EventBus（观察者模式，对应 README 3.1）。

同步订阅，但 publish 入队；本轮 dispatch 出栈后再投递下游，避免突破→走火入魔重入。
PlayTurnService 订阅 GameEventOccurrence。Clock / 日程 / matching 只 publish
Occurrence，不直调 pipeline。
"""
from __future__ import annotations

from collections import defaultdict
from typing import Callable, Protocol, TypeVar

E = TypeVar("E")


class EventBus(Protocol):
    def publish(self, event: object) -> None: ...
    def subscribe(self, event_type: type[E], handler: Callable[[E], None]) -> None: ...


class InProcessEventBus:
    """同步订阅，但 publish 入队；本轮 dispatch 出栈后再投递下游。"""

    def __init__(self) -> None:
        self._subs: dict[type, list[Callable]] = defaultdict(list)
        self._queue: list[object] = []
        self._flushing: bool = False

    def subscribe(self, event_type: type[E], handler: Callable[[E], None]) -> None:
        self._subs[event_type].append(handler)

    def publish(self, event: object) -> None:
        self._queue.append(event)
        if not self._flushing:
            self._flush()

    def _flush(self) -> None:
        self._flushing = True
        try:
            while self._queue:
                event = self._queue.pop(0)
                for handler in list(self._subs[type(event)]):
                    handler(event)
        finally:
            self._flushing = False
