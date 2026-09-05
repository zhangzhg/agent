"""model/repositories/llm/llm_result_text_parser.py — 编辑器"结果"文字描述（自然
语言）转结构化 result_pool，供手工编辑事件时用（替代直接写 result_pool JSON）。

拆两部分解析：
  1. 数值得失（金钱/饱食/修为/心魔）——直接转成 state_change，走
     model/services/result_pool_safety.py 的同一套安全白名单。
  2. 物品得失——不让模型直接编 item_id（十有八九是悬空引用），只让它抽取一句
     "这段话有没有提到获得某个具体物品，是什么"的自然语言描述（item_query），
     真正解析成 item_id 是调用方（admin_controller.py）拿这句描述去跟物品库做
     向量相似度匹配（model/services/item_embedding_match.py）的事——LLM 只管
     "有没有提到物品、提到的是什么"，不管"这是不是库里已有的东西"。

跟 llm_event_flavor_author.py 批量生成时顺带产出 result_pool 是同一套安全规则，
区别只是这里是单条、按需解析（保存时调一次，不是批量生成的一部分）。LLM 不可用/
解析失败时返回空结果——结果描述文字本身仍然会存下来（GameEventDef.result_text），
只是没有对应的机制效果，不阻塞保存。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Protocol

from model.services.result_pool_safety import FIELD_HINT, sanitize_result_pool

_logger = logging.getLogger("eventhorizon.llm_result_text_parser")


class LlmClient(Protocol):
    def complete(self, prompt: str) -> str: ...


@dataclass
class ParsedResult:
    state_changes: list[dict] = field(default_factory=list)
    item_query: str = ""  # 空字符串 = 没提到要获得具体物品


def _build_prompt(result_text: str) -> str:
    return (
        "你是一款文字修仙游戏的事件录入助手。下面是一条事件「结果」的自然语言描述，"
        "请把里面明确的数值得失和物品得失都提取出来。\n\n"
        "结果描述：\n" + result_text + "\n\n"
        "只输出一个 JSON 对象，不要有任何多余文字、解释或代码块标记（不要用 ```）。"
        '格式：{"state_changes": [...], "item_query": "..."}\n'
        'state_changes 是数值得失数组，没有就是 []，每个元素形如 '
        '{"kind": "state_change", "field": 下面选一个, "delta": 数值}，'
        "field 只能从这四个里选，不能自造：" + FIELD_HINT + "；最多给 3 条；\n"
        "item_query：如果结果描述里明确提到获得/得到/拿到了某个具体的实物物品"
        "（不是抽象的境界/金钱/状态变化），就用几个字概括这个物品是什么"
        "（比如\"一把锋利的长剑\"、\"一颗培元丹\"）；没有提到具体物品就给空字符串 \"\"。"
        "不要自己编一个 item_id——这里只描述物品是什么，不负责判断它是不是库里已有的东西。"
    )


class LlmResultTextParser:
    def __init__(self, client: LlmClient) -> None:
        self._client = client

    def parse(self, result_text: str) -> ParsedResult:
        result_text = result_text.strip()
        if not result_text:
            return ParsedResult()
        raw = self._client.complete(_build_prompt(result_text))
        parsed = _parse_json_object(raw)
        state_changes = sanitize_result_pool(parsed.get("state_changes"))
        item_query = str(parsed.get("item_query") or "").strip()
        return ParsedResult(state_changes=state_changes, item_query=item_query)


def _parse_json_object(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        _logger.warning("LLM output is not valid JSON, discarding result_text parse")
        return {}
    return parsed if isinstance(parsed, dict) else {}
