"""model/domain/predicates.py — 谓词白名单，替代 eval（对应 README 1.3.1）。

这份 PredicateGroup 同时服务三处：model/services/matching.py 粗筛、
model/services/scenario_executor.py 流程图边跳转、controller/editor_controller.py
的"模拟触发"沙盒——三处复用同一套定义，避免"编辑器和运行时两套标准"（README 1.3.3）。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol, Union


class PredicateType(str, Enum):
    ATTR_GTE = "attr_gte"
    ATTR_EQ = "attr_eq"
    REALM_GTE = "realm_gte"  # 境界有序比较，不用 float
    MONEY_GTE = "money_gte"
    AGE_GTE = "age_gte"
    HAS_ITEM = "has_item"
    FLAG = "flag"
    LOCATION_TYPE = "location_type"
    HAS_CAUSE = "has_cause"
    LUCK_GTE = "luck_gte"  # 隐藏谓词（GAME_DESIGN §7.5）：运势影响奇遇粗筛通过率，
    # 不进 README 公开谓词白名单，只供系统内置事件使用——event_validation.py 的
    # 编辑器/大模型录入校验会拒绝它，杜绝策划把"运势"当成可任意拼装的谓词滥用。


@dataclass(frozen=True, slots=True)
class Predicate:
    type: PredicateType
    args: tuple[Any, ...]


class EvalContext(Protocol):
    """粗筛/门控/流程图/录入沙盒共用。境界用 realm_gte，不用 attr 冒充。"""

    def attr(self, name: str) -> float: ...
    def realm_rank(self) -> int: ...
    def money(self) -> int: ...
    def age(self) -> int: ...
    def has_item(self, item_id: str) -> bool: ...
    def flag(self, name: str) -> bool: ...
    def location_type(self) -> str: ...
    def has_cause(self, tag: str, target: str) -> bool: ...


_EVALUATORS = {
    PredicateType.ATTR_GTE: lambda ctx, a: ctx.attr(a[0]) >= a[1],
    PredicateType.ATTR_EQ: lambda ctx, a: ctx.attr(a[0]) == a[1],
    PredicateType.REALM_GTE: lambda ctx, a: ctx.realm_rank() >= a[0],
    PredicateType.MONEY_GTE: lambda ctx, a: ctx.money() >= a[0],
    PredicateType.AGE_GTE: lambda ctx, a: ctx.age() >= a[0],
    PredicateType.HAS_ITEM: lambda ctx, a: ctx.has_item(a[0]),
    PredicateType.FLAG: lambda ctx, a: ctx.flag(a[0]),
    PredicateType.LOCATION_TYPE: lambda ctx, a: ctx.location_type() == a[0],
    PredicateType.HAS_CAUSE: lambda ctx, a: ctx.has_cause(a[0], a[1]),
    PredicateType.LUCK_GTE: lambda ctx, a: ctx.attr("luck") >= a[0],
}


def evaluate(p: Predicate, ctx: EvalContext) -> bool:
    return _EVALUATORS[p.type](ctx, p.args)


@dataclass(frozen=True, slots=True)
class PredicateGroup:
    """AND/OR 组合，禁止任意字符串 eval；录入编辑器的谓词构建器产出同一结构。"""

    op: str  # "AND" | "OR"
    items: tuple["PredicateOrGroup", ...]

    def evaluate(self, ctx: EvalContext) -> bool:
        results = (
            evaluate(i, ctx) if isinstance(i, Predicate) else i.evaluate(ctx)
            for i in self.items
        )
        return all(results) if self.op == "AND" else any(results)


PredicateOrGroup = Union[Predicate, PredicateGroup]
