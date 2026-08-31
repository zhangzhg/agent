"""model/repositories/llm/llm_event_author.py — 录入侧大模型（Adapter 模式，
仅录入侧，对应 README 1.3.4 / 5.3）。

对局隔离：PlayTurnService / ChatParser / matching 的构造函数禁止出现
LlmAuthorPort。该端口只注入录入用例。
"""
from __future__ import annotations

import json
import logging
from dataclasses import replace
from typing import TYPE_CHECKING, Protocol

from model.domain.events import GameEventDef
from model.services.event_validation import ValidationCatalog, validate_event_def

if TYPE_CHECKING:
    pass

_logger = logging.getLogger("eventhorizon.llm_event_author")


class LlmClient(Protocol):
    """录入侧对接的大模型客户端最小接口；具体供应商（Claude/GPT/…）在 controller
    组合根按需注入，本文件不绑定任何厂商 SDK。"""

    def complete(self, prompt: str) -> str: ...


DEFAULT_PROMPT_TEMPLATE = (
    "你是修仙游戏事件库的录入助手。根据下面的描述生成一条或多条事件草稿，"
    "严格输出 JSON 数组，每个元素是一条符合 GameEventDef 结构的对象"
    "（event_id/applicable_locations/predicate/weight/duration_shichen/cooldown_shichen/"
    "exclusive_tags/priority/tags/aliases/result_pool/variants，谓词与结果只能使用白名单类型）。\n"
    "描述：{description}\n约束：{constraints}\n"
)


class LlmEventAuthor:
    def __init__(self, client: LlmClient, prompt_template: str = DEFAULT_PROMPT_TEMPLATE, catalog: ValidationCatalog | None = None) -> None:
        self._client = client
        self._prompt_template = prompt_template
        self._catalog = catalog or ValidationCatalog()

    def generate_draft(self, description: str, constraints: dict) -> list[GameEventDef]:
        raw = self._client.complete(self._prompt_template.format(description=description, constraints=constraints))
        out: list[GameEventDef] = []
        for item in _parse_json_array(raw):
            # 调 §4.12 的公共校验，不在适配器里自己写一份
            defn, errors = validate_event_def(item, self._catalog)
            if defn is not None:
                out.append(replace(defn, is_draft=True))  # 一律先落草稿，人工发布才进合格池
            else:
                _report(item, errors)  # 标错字段返给编辑器，不整体入库
        return out


def _parse_json_array(raw: str) -> list[dict]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        _logger.warning("LLM output is not valid JSON, discarding draft batch")
        return []
    if isinstance(parsed, dict):
        parsed = [parsed]
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def _report(item: dict, errors: list) -> None:
    _logger.warning("draft %r failed validation: %s", item.get("event_id"), errors)
