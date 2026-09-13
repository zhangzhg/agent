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

# FIELD_HINT 里的"常见范围"只是 prompt 里给模型的措辞，从没在代码里真正强制过——
# 实测 glm-4-flash 有时会给出远超这个范围的数值（比如"买人参"给了 money delta
# -200/-100，而不是提示里的 -20~30），大概是被"标价不菲"这类叙事细节带偏，
# 没意识到这个字段其实有隐含上限。放行任意大小的 delta 有实际风险（一次事件就能
# 把玩家的钱清空/修为爆表），所以在这里按"常见范围"的 2 倍设一个硬上限——比提示
# 的常见范围宽松，给叙事留余地，但不能离谱到毁掉数值平衡。超界不丢弃整条，直接
# clamp 到边界，比丢弃更贴近模型原本的意图（它想表达"很贵/很有用"，只是数值离谱，
# clamp 到上限依然保留了"这次变化比较大"的方向和相对强度）。
_DELTA_CLAMP_RANGE = {
    "money": (-60.0, 60.0),
    "satiety": (-30.0, 30.0),
    "cultivation": (-60.0, 60.0),
    "heart_demon": (-0.2, 0.2),
}


def _clamp_delta(field: str, delta: float) -> float:
    lo, hi = _DELTA_CLAMP_RANGE.get(field, (-60.0, 60.0))
    return max(lo, min(hi, delta))


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
        out.append({"kind": "state_change", "field": field, "delta": _clamp_delta(field, delta)})
        if len(out) >= 3:  # 别让一条事件的 result_pool 堆得离谱长
            break
    return out


def sanitize_branch_results(raw_results) -> list[dict]:
    """live_content_author.py 的分支结果（ReplyOption.results）专用——比
    sanitize_result_pool 多放行一种 item_drop，因为分支的典型场景就是"要不要
    拿下一件具体的实物"（README 待补充章节：实时创作事件的分支结果）。

    item_id 不校验是否在物品目录里登记过：跟事件本身的 event_id（live_xxxxx）
    一样是这次对局临时创作、不经草稿审核的产物，Inventory 只是个
    dict[item_id, count]（model/domain/items.py），不要求 item_id 对应真实
    ItemDef；没有 ItemDef 时背包面板会直接拿 item_id 本身当显示名
    （view/inventory_panel_view.py），只要模型给的是一个可读的中文物品名当
    item_id，玩家看到的就是正常的物品名称，不会显示成一串乱码 id。"""
    if not isinstance(raw_results, list):
        return []
    out: list[dict] = []
    for entry in raw_results:
        if not isinstance(entry, dict):
            continue
        kind = entry.get("kind")
        if kind == "state_change":
            field = entry.get("field")
            if field not in SAFE_STATE_CHANGE_FIELDS:
                continue
            try:
                delta = float(entry.get("delta"))
            except (TypeError, ValueError):
                continue
            out.append({"kind": "state_change", "field": field, "delta": _clamp_delta(field, delta)})
        elif kind == "item_drop":
            item_id = entry.get("item_id")
            if not isinstance(item_id, str) or not item_id.strip():
                continue
            try:
                n = max(1, min(5, int(entry.get("n", 1))))
            except (TypeError, ValueError):
                n = 1
            out.append({"kind": "item_drop", "item_id": item_id.strip(), "n": n})
        else:
            continue
        if len(out) >= 3:
            break
    return out
