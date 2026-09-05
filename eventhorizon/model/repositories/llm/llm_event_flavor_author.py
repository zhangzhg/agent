"""model/repositories/llm/llm_event_flavor_author.py — 录入侧大模型：参考一段
情节/小说式描述，批量构思事件的"素材"（标签、聊天别名、叙事文案变体、权重/
时长/冷却/优先级，以及安全范围内的 result_pool），供事件页"AI 生成"按钮用。

跟 llm_event_author.py（README 5.3 文档里那个"完整结构化草稿生成器"）不是一回
事：那个要模型把 predicate 也一起编出来——谓词是递归判别联合类型，模型十有
八九编不出白名单内的合法组合，这里干脆不让模型碰 predicate（生成的事件一律
predicate=None，即"随时可能触发"，调用方/人工后续可以自己加条件）。

result_pool 只放开 state_change 这一种最简单、无外部引用的结果类型，且 field
只认 SAFE_STATE_CHANGE_FIELDS 这四个数值属性——item_drop/item_consume 需要引用
真实存在的 item_id，chain_event/start_scenario 需要引用真实存在的 event_id/
scenario_id，模型编的 id 十有八九是悬空引用，要么在 validate_event_def() 那关
被拒（浪费一次生成），要么万一 id 恰好撞对了却语义不对，更糟——所以从这里就
直接过滤掉，不指望校验层兜底。weight/duration_shichen/cooldown_shichen/
priority 允许模型给出建议值，但会按 content/events/*.py 里实际用到的数值范围
夹一遍，不让模型把权重开到离谱大小。
"""
from __future__ import annotations

import json
import logging
from typing import Protocol

from model.services.result_pool_safety import FIELD_HINT as _FIELD_HINT
from model.services.result_pool_safety import sanitize_result_pool

_logger = logging.getLogger("eventhorizon.llm_event_flavor_author")


class LlmClient(Protocol):
    def complete(self, prompt: str) -> str: ...


def _build_prompt(description: str, count: int) -> str:
    description = description.strip()
    if description:
        source_line = "情节描述：\n" + description + "\n\n"
        inspiration_note = "2. variants 给 1-2 条不同措辞的文案，都要呼应上面的情节描述；\n"
    else:
        # 情节描述留空 = 让 AI 自己发挥：不能就地卡壳、也不能敷衍写"这里发生了一些
        # 事"，明确要求它自己先构思一个具体场景再落笔，产出质量跟给了描述时应该
        # 是同一个水准。
        source_line = (
            "没有提供具体情节描述——请你自己先构思一个适合修仙世界观的具体场景或"
            "桥段（可以参考经典仙侠/武侠小说桥段，比如坊市淘宝、山门试炼、江湖恩怨、"
            "奇遇邂逅等），再落笔写文案，不要写成空泛笼统的套话。\n\n"
        )
        inspiration_note = "2. variants 给 1-2 条不同措辞的文案，都要落在你自己构思的具体场景里，不要写得空泛笼统；\n"
    return (
        "你是一款文字修仙游戏的事件录入助手。请参考下面这段情节描述（可以是一段小说"
        "式的场景、桥段或灵感），构思 " + str(count) + " 个可以在游戏里触发的生活/奇遇事件"
        "——尽量给出完整的数据，跟人工在编辑器里手填的事件一个水准，不要偷懒只写"
        "叙事文案。\n\n"
        + source_line +
        "只输出一个 JSON 数组，不要有任何多余文字、解释或代码块标记（不要用 ```）。"
        "数组每个元素形如：\n"
        '{"tags": ["奇遇"], "aliases": [], '
        '"variants": ["第二人称叙事文案，40-120字，古风白话文风格，读起来像小说片段"], '
        '"weight": 1.0, "duration_shichen": 1, "cooldown_shichen": 0, "priority": 5, '
        '"result_pool": [{"kind": "state_change", "field": "money", "delta": 5}], '
        '"item_query": ""}\n\n'
        "要求：\n"
        "1. tags 从「生活、修炼、社交、奇遇、战斗、经济」里选 1-2 个最贴切的；\n"
        + inspiration_note +
        "3. 文案里如果要用占位符，只能用这几个，不能自造：{地点} {境界} {金钱} {年龄} {天气} {对象}；\n"
        "4. aliases 一般留空数组即可，除非场景明确是玩家可以主动发起的动作（比如"
        "\"钓鱼\"），这种情况给 1-2 个玩家可能会打出来的动作短语；\n"
        "5. weight（触发权重，越大越容易被抽中）给 0.3~3 之间的数，越离奇稀有的事件权重"
        "越低，越日常的权重越高；\n"
        "6. duration_shichen（这段情节占用几个时辰）给 0~4 的整数；cooldown_shichen"
        "（同一角色隔多久才能再触发一次，单位时辰）给 0~24 的整数；priority 给 1~9 的"
        "整数（一般给 5）；\n"
        "7. result_pool 是这个事件实际造成的数值效果，情节里如果明确有得失（给钱、"
        "破财、修为长进、伤身耗神等）就写 1-2 条，没有实际影响就给空数组 []；每一条只能是 "
        '{"kind": "state_change", "field": 下面选一个, "delta": 数值}，field 只能从这'
        "四个里选，不能自造：" + _FIELD_HINT + "；不要用 item_drop/chain_event 等其它 kind"
        "（这些需要引用真实存在的物品/事件 id，你编不出合法的，写了也会被丢弃）；\n"
        "8. item_query：如果情节明确是玩家获得/得到/拿到了某个具体的实物物品，就用"
        "几个字概括这个物品是什么（比如\"一把锋利的长剑\"、\"一颗培元丹\"），没有提到"
        "具体物品就给空字符串 \"\"——不要自己编 item_id，这里只描述物品是什么。"
    )


def _clamp_float(value, default: float, lo: float, hi: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def _clamp_int(value, default: int, lo: int, hi: int) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


class LlmEventFlavorAuthor:
    def __init__(self, client: LlmClient) -> None:
        self._client = client

    def generate_event_flavors(self, description: str, count: int) -> list[dict]:
        """返回 [{"tags":[...], "aliases":[...], "variants":[...], "weight":...,
        "duration_shichen":..., "cooldown_shichen":..., "priority":...,
        "result_pool":[...], "item_query":...}, ...]，已过滤掉没有任何有效
        variants 文本的条目、数值字段已夹到安全范围内、result_pool 已过滤成只剩
        安全的 state_change 条目；item_query 是"这个事件是否提到获得具体物品"的
        自然语言描述（空字符串=没提到），调用方（admin_controller.py）拿它去跟
        物品库做向量匹配、解析成真正的 item_drop——这里不负责判断物品是否存在。
        数量可能比 count 少。"""
        prompt = _build_prompt(description, count)
        raw = self._client.complete(prompt)
        items = _parse_json_array(raw)
        out: list[dict] = []
        for item in items:
            variants = [str(v).strip() for v in item.get("variants", []) if str(v).strip()]
            if not variants:
                continue
            tags = [str(t).strip() for t in item.get("tags", []) if str(t).strip()]
            aliases = [str(a).strip() for a in item.get("aliases", []) if str(a).strip()]
            out.append({
                "tags": tags,
                "aliases": aliases,
                "variants": variants,
                "weight": _clamp_float(item.get("weight"), default=1.0, lo=0.1, hi=5.0),
                "duration_shichen": _clamp_int(item.get("duration_shichen"), default=1, lo=0, hi=8),
                "cooldown_shichen": _clamp_int(item.get("cooldown_shichen"), default=0, lo=0, hi=48),
                "priority": _clamp_int(item.get("priority"), default=5, lo=1, hi=9),
                "result_pool": sanitize_result_pool(item.get("result_pool")),
                "item_query": str(item.get("item_query") or "").strip(),
            })
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
