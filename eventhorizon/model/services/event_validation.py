"""model/services/event_validation.py — 编辑器与大模型共用的校验（对应 README 1.3.3 /
4.12）。

校验属于业务规则，必须放在 services，由 editor_controller（手工保存）与
LlmEventAuthor（草稿生成）共同调用同一个函数。原设计把 _validate_and_build 私有
在 LLM 适配器里，等于逼编辑器再写一份——两份校验一旦漂移，就退回到 README 1.3.3
明令禁止的"编辑器与运行时两套标准"。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from model.domain.events import EventVariant, GameEventDef, ReplyOption
from model.domain.predicates import Predicate, PredicateGroup, PredicateType
from model.domain.results import (
    ChainEvent,
    Check,
    FlagClear,
    FlagSet,
    ItemConsume,
    ItemDrop,
    StartScenario,
    StateChange,
    WriteCause,
)
from model.domain.scenario import ScenarioGraph

_PREDICATE_ARITY = {
    PredicateType.ATTR_GTE: 2,
    PredicateType.ATTR_EQ: 2,
    PredicateType.REALM_GTE: 1,
    PredicateType.MONEY_GTE: 1,
    PredicateType.AGE_GTE: 1,
    PredicateType.HAS_ITEM: 1,
    PredicateType.FLAG: 1,
    PredicateType.LOCATION_TYPE: 1,
    PredicateType.HAS_CAUSE: 2,
    PredicateType.LUCK_GTE: 1,
}
_INTERNAL_ONLY_PREDICATE_TYPES = {PredicateType.LUCK_GTE}  # 隐藏谓词（GAME_DESIGN §7.5）：
# 只供系统内置事件在 Python 里直接构造 Predicate 使用，编辑器/LlmEventAuthor 提交的
# JSON 一律拒绝，避免运势谓词被随意暴露给策划拼装。
_DISALLOWED_DIRECT_FIELDS = ("money", "realm", "境界", "金钱")
_PLACEHOLDER_RE = re.compile(r"\{([^{}]+)\}")


@dataclass
class FieldError:
    field: str
    message: str


@dataclass
class ValidationCatalog:
    """联动校验的引用来源：物品 ID / eventId / scenarioId 是否存在，占位符白名单。"""

    known_item_ids: set[str] = field(default_factory=set)
    known_event_ids: set[str] = field(default_factory=set)
    known_scenario_ids: set[str] = field(default_factory=set)
    placeholder_whitelist: set[str] = field(
        default_factory=lambda: {"地点", "境界", "金钱", "年龄", "天气", "对象"}
    )


def validate_event_def(raw: dict, ctx: ValidationCatalog) -> tuple[GameEventDef | None, list[FieldError]]:
    """README 1.3.3 联动校验的唯一实现：
      - 谓词类型在白名单内、参数元数类型匹配
      - item_id / chain event_id / scenario_id 引用存在
      - 流程图无孤立节点与环、边不跨 scenario
      - 互斥标签不与自身冲突；变体占位符在白名单内
      - 金钱/境界只许走 Result 类型，不许直写字段
    """
    errors: list[FieldError] = []

    for bad_key in _DISALLOWED_DIRECT_FIELDS:
        if bad_key in raw:
            errors.append(FieldError(bad_key, "金钱/境界只许走 Result 类型（StateChange），不许直写字段"))

    event_id = raw.get("event_id")
    if not event_id or not isinstance(event_id, str):
        errors.append(FieldError("event_id", "event_id 必填且必须是字符串"))

    exclusive_tags = tuple(raw.get("exclusive_tags", ()))
    tags = tuple(raw.get("tags", ()))
    if set(exclusive_tags) & set(tags):
        errors.append(FieldError("exclusive_tags", "互斥标签不能与自身 tags 冲突"))

    predicate = None
    if raw.get("predicate") is not None:
        predicate = _build_predicate(raw["predicate"], "predicate", errors)

    result_pool = tuple(_build_result(item, f"result_pool[{i}]", ctx, errors) for i, item in enumerate(raw.get("result_pool", ())))
    result_pool = tuple(r for r in result_pool if r is not None)

    variants_raw = raw.get("variants", ())
    if not variants_raw:
        errors.append(FieldError("variants", "至少要求 1 条默认文案"))
    variants = []
    for i, v in enumerate(variants_raw):
        text = v.get("text", "")
        for placeholder in _PLACEHOLDER_RE.findall(text):
            if placeholder not in ctx.placeholder_whitelist:
                errors.append(FieldError(f"variants[{i}].text", f"占位符 {{{placeholder}}} 不在白名单内"))
        variants.append(EventVariant(text=text, weight=v.get("weight", 1.0)))

    reply_options = tuple(
        ReplyOption(
            aliases=tuple(ro.get("aliases", ())),
            results=tuple(_build_result(r, f"reply_options[{i}].results", ctx, errors) for r in ro.get("results", ()) if r),
            chain_event_id=_check_event_ref(ro.get("chain_event_id"), f"reply_options[{i}].chain_event_id", ctx, errors),
            response_text=ro.get("response_text", ""),
        )
        for i, ro in enumerate(raw.get("reply_options", ()))
    )

    scenario_ref = raw.get("scenario_ref")
    if scenario_ref is not None and scenario_ref not in ctx.known_scenario_ids:
        errors.append(FieldError("scenario_ref", f"scenario_id {scenario_ref!r} 不存在"))

    if errors:
        return None, errors

    defn = GameEventDef(
        event_id=event_id,
        applicable_locations=tuple(raw.get("applicable_locations", ("*",))),
        applicable_time=tuple(raw["applicable_time"]) if raw.get("applicable_time") is not None else None,
        predicate=predicate,
        weight=float(raw.get("weight", 1.0)),
        duration_shichen=int(raw.get("duration_shichen", 1)),
        cooldown_shichen=int(raw.get("cooldown_shichen", 0)),
        max_trigger_per_agent=raw.get("max_trigger_per_agent"),
        exclusive_tags=exclusive_tags,
        priority=int(raw.get("priority", 5)),
        tags=tags,
        aliases=tuple(raw.get("aliases", ())),
        result_pool=result_pool,
        variants=tuple(variants),
        reply_options=reply_options,
        novelty_curve_override=raw.get("novelty_curve_override"),
        scenario_ref=scenario_ref,
        schema_version=int(raw.get("schema_version", 1)),
        is_draft=bool(raw.get("is_draft", True)),
        is_command=bool(raw.get("is_command", False)),
    )
    return defn, []


def validate_scenario_graph(graph: ScenarioGraph) -> list[FieldError]:
    """流程图结构校验：孤立节点、环。跨 scenario 引用在 ScenarioGraph 构造时已拒绝。"""
    errors = []
    if graph.has_orphan_nodes():
        errors.append(FieldError("scenario.nodes", "存在孤立节点（没有任何入边，且不是入口节点）"))
    if graph.has_cycle():
        errors.append(FieldError("scenario.edges", "流程图存在环"))
    return errors


def _build_predicate(raw: dict, path: str, errors: list[FieldError]):
    op = raw.get("op")
    if op in ("AND", "OR"):
        items = tuple(
            _build_predicate(item, f"{path}.items[{i}]", errors) for i, item in enumerate(raw.get("items", ()))
        )
        return PredicateGroup(op=op, items=tuple(i for i in items if i is not None))
    type_name = raw.get("type")
    try:
        ptype = PredicateType(type_name)
    except ValueError:
        errors.append(FieldError(path, f"未知谓词类型 {type_name!r}，不在白名单内"))
        return None
    if ptype in _INTERNAL_ONLY_PREDICATE_TYPES:
        errors.append(FieldError(path, f"谓词类型 {type_name!r} 仅供系统内置事件使用，编辑器/大模型录入不可用"))
        return None
    args = tuple(raw.get("args", ()))
    if len(args) != _PREDICATE_ARITY[ptype]:
        errors.append(FieldError(path, f"谓词 {type_name} 需要 {_PREDICATE_ARITY[ptype]} 个参数，实际 {len(args)} 个"))
        return None
    return Predicate(type=ptype, args=args)


def _check_item_ref(item_id: str, path: str, ctx: ValidationCatalog, errors: list[FieldError]) -> str:
    if ctx.known_item_ids and item_id not in ctx.known_item_ids:
        errors.append(FieldError(path, f"item_id {item_id!r} 不存在（可先标为「待补物品」草稿）"))
    return item_id


def _check_event_ref(event_id: str | None, path: str, ctx: ValidationCatalog, errors: list[FieldError]) -> str | None:
    if event_id is None:
        return None
    if ctx.known_event_ids and event_id not in ctx.known_event_ids:
        errors.append(FieldError(path, f"eventId {event_id!r} 不存在"))
    return event_id


def _build_result(raw: dict, path: str, ctx: ValidationCatalog, errors: list[FieldError]):
    kind = raw.get("kind")
    if kind == "item_drop":
        return ItemDrop(item_id=_check_item_ref(raw["item_id"], f"{path}.item_id", ctx, errors), n=raw.get("n", 1))
    if kind == "item_consume":
        return ItemConsume(item_id=_check_item_ref(raw["item_id"], f"{path}.item_id", ctx, errors), n=raw.get("n", 1))
    if kind == "state_change":
        return StateChange(field=raw["field"], delta=raw.get("delta"), set_to=raw.get("set_to"))
    if kind == "check":
        on_success = tuple(_build_result(r, f"{path}.on_success", ctx, errors) for r in raw.get("on_success", ()))
        on_fail = tuple(_build_result(r, f"{path}.on_fail", ctx, errors) for r in raw.get("on_fail", ()))
        return Check(kind=raw["check_kind"], on_success=tuple(r for r in on_success if r), on_fail=tuple(r for r in on_fail if r))
    if kind == "write_cause":
        return WriteCause(tag=raw["tag"], target=raw["target"], expires_years=raw.get("expires_years"))
    if kind == "chain_event":
        from model.domain.events import TriggerSource

        event_id = _check_event_ref(raw["event_id"], f"{path}.event_id", ctx, errors)
        source = TriggerSource(raw.get("source_override", "chain"))
        return ChainEvent(event_id=event_id, source_override=source)
    if kind == "start_scenario":
        scenario_id = raw["scenario_id"]
        if ctx.known_scenario_ids and scenario_id not in ctx.known_scenario_ids:
            errors.append(FieldError(f"{path}.scenario_id", f"scenario_id {scenario_id!r} 不存在"))
        return StartScenario(scenario_id=scenario_id)
    if kind == "flag_set":
        return FlagSet(name=raw["name"])
    if kind == "flag_clear":
        return FlagClear(name=raw["name"])
    errors.append(FieldError(path, f"未知结果类型 {kind!r}"))
    return None
