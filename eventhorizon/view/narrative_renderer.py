"""view/narrative_renderer.py — 叙述文本拼装（对应 README §6）。

view 只消费 TurnResult 与 AppliedDiff，禁止 import PipelineContext。
"""
from __future__ import annotations

import string
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from model.domain.events import GameEventDef
    from model.domain.map import LocationCondition
    from model.services.turn_result import TurnResult

_FORMATTER = string.Formatter()

_RUIN_NARRATIVE_HOOKS = ("断壁残垣间尚有余烬味。", "焦土之上，草木未生。", "残垣断壁，一片萧索。")


class _Defaulting(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def safe_format(text: str, placeholders: dict) -> str:
    """容错渲染：未知占位符原样保留，花括号写错不抛异常。
    渲染发生在状态已改、日志已写之后——这里抛 KeyError 会让整个回合看起来失败，
    实际却已经扣了钱。占位符白名单在录入时由 §4.12 校验，这里只兜底。"""
    try:
        return _FORMATTER.vformat(text, (), _Defaulting(placeholders))
    except Exception:
        return text


def render_turn(
    result: "TurnResult",
    defs: dict[str, "GameEventDef"],
    placeholders: dict,
    location_condition: "LocationCondition | None" = None,
) -> str:
    """location_condition：GAME_DESIGN §5.3——废墟态地点固定插入环境描写钩子，
    不需要额外 UI 标记，玩家从叙述本身就能判断"这里发生过事"。"""
    if result.parse_error:
        return result.parse_error
    if result.reject_reason:
        return result.reject_reason
    if result.retreat_summary is not None:
        from view.retreat_view import render_retreat_summary

        return render_retreat_summary(
            result.retreat_summary, result.retreat_before_realm or "", result.retreat_before_cultivation or 0.0
        )
    parts = []
    if result.freeform_narrative:
        # 前缀行，不是独占返回：像"你付了钱……"这类选项应答，后面通常还跟着链式
        # 事件自己的叙述（encounter_event_id），两句话都要出现，不能互相顶掉。
        parts.append(result.freeform_narrative)
    if _is_ruined(location_condition):
        # 用地点名的字符和取一个稳定下标，不依赖 hash()（Python 默认对字符串做哈希
        # 随机化，同一进程内虽稳定，但换个写法更直白，也避免给人"这里在用随机数"的错觉）。
        location_name = placeholders.get("地点", "")
        pick = sum(ord(ch) for ch in location_name) % len(_RUIN_NARRATIVE_HOOKS)
        parts.append(_RUIN_NARRATIVE_HOOKS[pick])
    if result.command_event_id:
        defn = defs.get(result.command_event_id)
        if defn is not None:
            parts.append(safe_format(defn.variants[result.command_variant].text, placeholders))
    if result.encounter_event_id:
        defn = defs.get(result.encounter_event_id)
        if defn is not None:
            parts.append(safe_format(defn.variants[result.encounter_variant].text, placeholders))
    if result.prompt_event_id:  # 挂起提示：奇遇已叙述、等玩家下一句
        defn = defs.get(result.prompt_event_id)
        if defn is not None:
            parts.append(safe_format(defn.variants[result.prompt_variant].text, placeholders))
    if not parts:
        return "无事发生。"
    return "\n".join(parts)


def _is_ruined(location_condition: "LocationCondition | None") -> bool:
    return location_condition is not None and location_condition.value == "废墟"


def placeholders_from(agent) -> dict:
    """从 Agent 组装占位符白名单里约定的那几个字段（地点/境界/金钱/年龄/天气/对象）。"""
    return {
        "地点": agent.location_id,
        "境界": agent.realm,
        "金钱": agent.money,
        "年龄": agent.age,
        "对象": agent.scene_focus or "",
    }
