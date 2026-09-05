"""model/repositories/llm/llm_item_author.py — 录入侧大模型：按类型/数量批量生成
物品草稿（名称 + 描述），供物品页"AI 生成"按钮用。跟 llm_location_author.py 一样
是 Adapter，只在录入用例里注入，不参与对局（README 5.3 对局隔离）。

stackable/unique 这些不是"编"出来的属性，是按 kind 的固定规则派生（丹药/食材/
材料默认可堆叠，秘籍/装备默认不可堆叠），不让模型决定——理由跟地点生成器里
灵气浓度/危险等级不让模型编一样：这类会影响背包/交易逻辑的机制字段该有稳定
可预期的默认值，模型只负责它擅长的部分——名字和一句话描述。
"""
from __future__ import annotations

import json
import logging
from typing import Protocol

_logger = logging.getLogger("eventhorizon.llm_item_author")

# ItemKind 的完整取值集合（model/domain/items.py）。类型留空 = 不限定，从这个
# 完整集合里自由发挥，跟事件生成器"情节描述留空 = 交给 AI 自己构思"是同一个思路。
ALL_ITEM_KINDS = ("food", "pill", "manual", "material", "gear")


class LlmClient(Protocol):
    def complete(self, prompt: str) -> str: ...


def _build_prompt(kinds: list[str], count: int, novel: str) -> str:
    novel = novel.strip()
    if novel:
        # 参考的是"世界观/命名风格"，不是照抄书里的原创物品名——直接搬用现成专有
        # 名词既没意思（批量生成一堆"重楼的养元丹"没意义），也容易撞车已有作品里
        # 读者能认出来的招牌道具，让模型自己原创、只学个神似。
        style_note = (
            "请参考小说《" + novel + "》的世界观设定和物品命名风格来构思，"
            "但物品名称必须是你自己原创的，不要直接使用《" + novel + "》书中已经出现过的"
            "专有物品名称（避免重名）。\n"
        )
    else:
        style_note = ""
    return (
        "你是一款文字修仙游戏的物品录入助手。" + style_note +
        "请构思 " + str(count) + " 个游戏物品，每个物品的 kind "
        "字段必须严格从下面这个集合里选一个（不要用集合外的词、不要翻译成英文）：\n"
        + "、".join(kinds) + "\n"
        "只输出一个 JSON 数组，不要有任何多余文字、解释或代码块标记（不要用 ```）。"
        '数组每个元素形如：{"name": "物品名，2-6个汉字，符合修仙世界观", '
        '"kind": "上面集合中的一个类型", "description": "一句话描述，20字以内，不要出现具体数值"}。'
        + str(count) + " 个物品的 name 互不重复。"
    )


class LlmItemAuthor:
    def __init__(self, client: LlmClient) -> None:
        self._client = client

    def generate_items(self, kinds: list[str], count: int, novel: str = "") -> list[dict]:
        """kinds 留空表示不限定类型，模型可以在全部 ItemKind 里自由发挥（用
        ALL_ITEM_KINDS 顶上，而不是拿一个空集合去要求"必须从里面选一个"——那样
        提示词本身就是自相矛盾的）。novel 留空表示不特别参考某部小说的风格。
        返回 [{"name":..., "kind":..., "description":...}, ...]，已过滤掉 kind
        不在白名单、name 为空、或本批次内重名的条目；数量可能比 count 少，调用方
        自己兜底补足。"""
        kinds = list(kinds) if kinds else list(ALL_ITEM_KINDS)
        prompt = _build_prompt(kinds, count, novel)
        raw = self._client.complete(prompt)
        items = _parse_json_array(raw)
        kind_set = set(kinds)
        seen_names: set[str] = set()
        out: list[dict] = []
        for item in items:
            name = str(item.get("name", "")).strip()
            kind = str(item.get("kind", "")).strip()
            description = str(item.get("description", "")).strip()
            if not name or kind not in kind_set or name in seen_names:
                continue
            seen_names.add(name)
            out.append({"name": name, "kind": kind, "description": description})
        return out


def _parse_json_array(raw: str) -> list[dict]:
    text = raw.strip()
    if text.startswith("```"):
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
