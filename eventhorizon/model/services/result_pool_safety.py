"""model/services/result_pool_safety.py — AI/自然语言产出的 result_pool 安全过滤，
被 model/repositories/llm/llm_event_flavor_author.py（批量生成事件）和
llm_result_text_parser.py（编辑器"结果"文字描述转结构化数据）共用，不各写一份。

只放行 state_change 且 field 在安全白名单内的条目——item_drop/item_consume 需要
引用真实存在的 item_id，chain_event/start_scenario 需要引用真实存在的
event_id/scenario_id，AI 或自然语言解析编出来的 id 十有八九是悬空引用，要么在
validate_event_def() 那关被拒（浪费一次生成/保存），要么万一 id 恰好撞对了却
语义不对，更糟——所以从这里就直接过滤掉，不指望校验层兜底。
"""
from __future__ import annotations

# Agent（model/domain/agent.py）里数值型、适合被"一次生活事件"随手改动的属性。
# 不包括 age/lifespan_left（寿元/年龄通常由专门的系统性事件调整，不该被一次随手
# 生成的奇遇事件动）、也不包括 aptitude/luck/insight（先天属性，改起来影响面更大，
# 更适合稀有内容手工把关）——四个都是 content/events/*.py 里实际在用的字段
# （用 tests/model/services/test_result_pool_safety.py 里的交叉检查防止两边写法漂移）。
SAFE_STATE_CHANGE_FIELDS = ("money", "satiety", "cultivation", "heart_demon")

FIELD_HINT = (
    "money（金钱，常见范围 -20~30）、satiety（饱食度，常见范围 -10~20）、"
    "cultivation（修为，常见范围 -20~30）、heart_demon（心魔，越低越好，常见范围 -0.05~0.1）"
)


def sanitize_result_pool(raw_pool) -> list[dict]:
    if not isinstance(raw_pool, list):
        return []
    out: list[dict] = []
    for entry in raw_pool:
        if not isinstance(entry, dict) or entry.get("kind") != "state_change":
            continue
        field = entry.get("field")
        if field not in SAFE_STATE_CHANGE_FIELDS:
            continue
        try:
            delta = float(entry.get("delta"))
        except (TypeError, ValueError):
            continue
        out.append({"kind": "state_change", "field": field, "delta": delta})
        if len(out) >= 3:  # 别让一条事件的 result_pool 堆得离谱长
            break
    return out
