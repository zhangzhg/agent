"""model/repositories/llm/llm_location_author.py — 录入侧大模型：按类型/数量批量
生成地点草稿（名称 + 类型），供地图编辑器"AI 生成"按钮用。跟 llm_event_author.py
一样是 Adapter，只在录入用例里注入，不参与对局（README 5.3 对局隔离），也不绑定
具体厂商 SDK——真正的 HTTP 客户端在 openai_compatible_client.py。

数值型属性（灵气浓度/危险等级等）不让模型编：那些是游戏平衡参数，交给调用方按
kind 用固定区间随机取（跟本地兜底生成器用的是同一套区间），LLM 只负责它更擅长的
部分——起一个符合世界观、不重复的名字。
"""
from __future__ import annotations

import json
import logging
from typing import Protocol

_logger = logging.getLogger("eventhorizon.llm_location_author")


class LlmClient(Protocol):
    """跟 llm_event_author.py 里的同名 Protocol 结构一致（鸭子类型），复用同一个
    OpenAiCompatibleClient 实现即可，这里不 import 那边的类型——两个 Adapter 各自
    只依赖它需要的最小接口，互不耦合。"""

    def complete(self, prompt: str) -> str: ...


PROMPT_TEMPLATE = (
    "你是一款文字修仙游戏的地图录入助手。请构思 {count} 个游戏地点，每个地点的"
    "kind 字段必须严格从下面这个集合里选一个（不要用集合外的词、不要翻译成英文）：\n"
    "{kinds}\n"
    "只输出一个 JSON 数组，不要有任何多余文字、解释或代码块标记（不要用 ```）。"
    "数组每个元素形如：{{\"name\": \"地点名，2-6个汉字，符合修仙世界观，读起来像地名\", "
    "\"kind\": \"上面集合中的一个类型\"}}。{count} 个地点的 name 互不重复。"
)


class LlmLocationAuthor:
    def __init__(self, client: LlmClient, prompt_template: str = PROMPT_TEMPLATE) -> None:
        self._client = client
        self._prompt_template = prompt_template

    def generate_locations(self, kinds: list[str], count: int) -> list[dict]:
        """返回 [{"name": ..., "kind": ...}, ...]，已经过滤掉 kind 不在白名单里、
        名字为空、或本批次内重名的条目——调用方不用再校验一遍，但仍然可能比 count
        少（模型没给够、或给的里面有一部分被过滤掉了），调用方要自己兜底补足。"""
        prompt = self._prompt_template.format(count=count, kinds="、".join(kinds))
        try:
            raw = self._client.complete(prompt)
        except Exception:
            _logger.exception("LLM complete() 调用失败")
            raise
        items = _parse_json_array(raw)
        kind_set = set(kinds)
        seen_names: set[str] = set()
        out: list[dict] = []
        for item in items:
            name = str(item.get("name", "")).strip()
            kind = str(item.get("kind", "")).strip()
            if not name or kind not in kind_set or name in seen_names:
                continue
            seen_names.add(name)
            out.append({"name": name, "kind": kind})
        return out


def _parse_json_array(raw: str) -> list[dict]:
    text = raw.strip()
    if text.startswith("```"):
        # 有些模型即使明确要求"不要代码块"也照样包一层 ```json ... ```，剥掉。
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        _logger.warning("LLM output is not valid JSON, discarding batch")
        return []
    if isinstance(parsed, dict):
        parsed = [parsed]
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]
