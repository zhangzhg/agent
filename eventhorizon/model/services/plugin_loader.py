"""model/services/plugin_loader.py — 插件模式（对应 README 3.5）。

MVP 只用 load_static：编译期静态注册，代码里显式列出，不做运行时热加载。
插件只能拿到 EventRegistry 引用，拿不到 EventBus/EventArbiter/clock_service——
构造函数签名上就不传，杜绝插件旁路核心规则。
"""
from __future__ import annotations

import importlib
import logging
from typing import Callable

from model.services.registry import EventRegistry

_logger = logging.getLogger("eventhorizon.plugin_loader")


class PluginLoader:
    def __init__(self, registry: EventRegistry) -> None:
        self._registry = registry

    def load_static(self, register_fns: list[Callable[[EventRegistry], None]]) -> None:
        """MVP：编译期静态注册，代码里显式列出，不做运行时热加载。"""
        for fn in register_fns:
            fn(self._registry)

    def load_manifest(self, manifest: list[dict]) -> None:
        """V1+：{module, register_fn} 清单，用 importlib 动态加载。"""
        for item in manifest:
            try:
                module = importlib.import_module(item["module"])
                getattr(module, item["register_fn"])(self._registry)
            except Exception as exc:
                # 失败隔离：单个插件加载失败不影响已注册核心事件
                _log_plugin_failure(item["module"], exc)


def _log_plugin_failure(module_name: str, exc: Exception) -> None:
    _logger.warning("plugin %r failed to load: %s", module_name, exc)
