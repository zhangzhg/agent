"""model/services/handlers/game_event_handler.py — 库内一般事件共用策略
（对应 README 3.2）。

事件库一般事件共用一个策略：eat/meditate/breakthrough/奇遇同一个类，差异只来自
ctx.event_def.result_pool，不写 switch。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from model.services.handlers.result_pool_executor import ResultPoolExecutor
    from model.services.pipeline import PipelineContext


class EventHandler(Protocol):
    def handle(self, ctx: "PipelineContext") -> None: ...


class GameEventHandler:
    """事件库一般事件共用一个策略：eat/meditate/breakthrough/奇遇同一个类。"""

    def __init__(self, result_pool_executor: "ResultPoolExecutor") -> None:
        self._executor = result_pool_executor

    def handle(self, ctx: "PipelineContext") -> None:
        for entry in ctx.event_def.result_pool:
            self._executor.execute(entry, ctx)
