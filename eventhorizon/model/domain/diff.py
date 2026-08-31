"""model/domain/diff.py — 差分（唯一改状态处，对应 README 1.8 / 3.3.1）。

结果池只计算 diff，不直接改 Agent / World。apply_agent_diff / apply_world_diff /
merge 是全系统唯一改 Agent / World 的地方——实时对局与读档重放调用的是同一份函数，
不存在"实时一套、回放一套"。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from model.domain.cause import CauseLink

if TYPE_CHECKING:
    from model.domain.agent import Agent, PendingScenario
    from model.domain.map import WorldState


@dataclass(frozen=True, slots=True)
class AppliedDiff:
    """Agent 级差分。数值一律走 attr_deltas，不写死字段清单——
    修为/心魔/寿元/悟性等后天属性都从这里过，避免加一个属性就改一次结构。"""

    attr_deltas: tuple[tuple[str, float], ...] = ()  # ("satiety", +3) ("money", -5) ("cultivation", +12)
    realm_set: str | None = None  # 境界是有序枚举，不当 float 加减
    location_set: str | None = None
    location_type_set: str | None = None  # 随 location_set 同步写入，否则粗筛用的
    # agent.location_type 会在移动后过期（ResultPoolExecutor 处理 StateChange(field="location")
    # 时用 WorldView 查一次目标地点类型一并写入，而不是让调用方各自记得同步两个字段）
    items_add: tuple[tuple[str, int], ...] = ()
    items_remove: tuple[tuple[str, int], ...] = ()
    flags_set: tuple[str, ...] = ()
    flags_clear: tuple[str, ...] = ()
    causes_add: tuple[CauseLink, ...] = ()
    time_shichen_delta: int = 0
    scene_focus_set: str | None = None
    pending_encounter_set: str | None = None  # 空串 "" 表示显式清空（None 表示"本次未涉及"）
    pending_scenario_set: "PendingScenario | None | str" = "__unset__"  # "__unset__" 哨兵：未涉及；None：显式清空
    state_set: str | None = None  # 状态机结果也进 diff，重放才能还原挂起态
    pending_retreat_prompt_set: bool | None = None  # 闭关"要多久"追问的挂起标记（GAME_DESIGN §4.3）


_UNSET = "__unset__"


@dataclass(frozen=True, slots=True)
class LocationAttrChange:
    location_id: str
    key: str  # qi_density | danger_level | condition | discovered
    old: float | str | bool  # 记 old 才能反向回滚（README 1.8 焦土复原）
    new: float | str | bool


@dataclass(frozen=True, slots=True)
class WorldDiff:
    """世界级差分。地图改动落在快照之后时，只有它能让重放不丢。"""

    location_changes: tuple[LocationAttrChange, ...] = ()

    def invert(self) -> "WorldDiff":
        return WorldDiff(tuple(
            LocationAttrChange(c.location_id, c.key, c.new, c.old) for c in self.location_changes
        ))


def merge(a: AppliedDiff, b: AppliedDiff) -> AppliedDiff:
    """把 b 叠加到 a 上。数值型字段相加；单值字段"后写覆盖"（TODO #3 已知冲突语义，
    录入校验时应对同回合双写 realm_set/location_set 告警）。"""
    deltas: dict[str, float] = {}
    for key, value in (*a.attr_deltas, *b.attr_deltas):
        deltas[key] = deltas.get(key, 0.0) + value

    pending_scenario = b.pending_scenario_set if b.pending_scenario_set != _UNSET else a.pending_scenario_set

    return AppliedDiff(
        attr_deltas=tuple(deltas.items()),
        realm_set=b.realm_set if b.realm_set is not None else a.realm_set,
        location_set=b.location_set if b.location_set is not None else a.location_set,
        location_type_set=b.location_type_set if b.location_type_set is not None else a.location_type_set,
        items_add=a.items_add + b.items_add,
        items_remove=a.items_remove + b.items_remove,
        flags_set=tuple(dict.fromkeys(a.flags_set + b.flags_set)),
        flags_clear=tuple(dict.fromkeys(a.flags_clear + b.flags_clear)),
        causes_add=a.causes_add + b.causes_add,
        time_shichen_delta=a.time_shichen_delta + b.time_shichen_delta,
        scene_focus_set=b.scene_focus_set if b.scene_focus_set is not None else a.scene_focus_set,
        pending_encounter_set=b.pending_encounter_set if b.pending_encounter_set is not None else a.pending_encounter_set,
        pending_scenario_set=pending_scenario,
        state_set=b.state_set if b.state_set is not None else a.state_set,
        pending_retreat_prompt_set=(
            b.pending_retreat_prompt_set if b.pending_retreat_prompt_set is not None else a.pending_retreat_prompt_set
        ),
    )


def apply_agent_diff(agent: "Agent", d: AppliedDiff) -> None:
    """全系统唯一改 Agent 的地方之一。数值走 attr_deltas，物品走 items_add/remove，
    标志/因果/挂起字段/状态各自累加或覆盖。"""
    for name, delta in d.attr_deltas:
        setattr(agent, name, getattr(agent, name) + delta)
    if d.realm_set is not None:
        agent.realm = d.realm_set
    if d.location_set is not None:
        agent.location_id = d.location_set
    if d.location_type_set is not None:
        agent.location_type = d.location_type_set
    for item_id, n in d.items_add:
        agent.inventory.add(item_id, n)
    for item_id, n in d.items_remove:
        agent.inventory.consume(item_id, n)
    for flag_name in d.flags_set:
        agent.flags.add(flag_name)
    for flag_name in d.flags_clear:
        agent.flags.discard(flag_name)
    if d.causes_add:
        agent.causes.extend(d.causes_add)
    if d.time_shichen_delta:
        agent.time_anchor.advance(d.time_shichen_delta)
    if d.scene_focus_set is not None:
        agent.scene_focus = None if d.scene_focus_set == "" else d.scene_focus_set
    if d.pending_encounter_set is not None:
        agent.pending_encounter_id = None if d.pending_encounter_set == "" else d.pending_encounter_set
    if d.pending_scenario_set != _UNSET:
        agent.pending_scenario = d.pending_scenario_set
    if d.state_set is not None:
        from model.domain.states import state_by_name

        agent.state = state_by_name(d.state_set)
    if d.pending_retreat_prompt_set is not None:
        agent.pending_retreat_prompt = d.pending_retreat_prompt_set


_LOCATION_ATTR_FIELDS = {"qi_density", "danger_level", "condition", "discovered"}


def apply_world_diff(world: "WorldState", d: WorldDiff) -> None:
    """全系统唯一改 WorldState 的地方。主要由 pipeline.ApplyDiffStep 调用；少数独立于
    责任链之外的只读探索类服务（如神识扫描发现隐藏点位）也经此写入，但同样不允许
    绕过它直接 setattr。"""
    for change in d.location_changes:
        location = world.get(change.location_id)
        if location is None or change.key not in _LOCATION_ATTR_FIELDS:
            continue
        setattr(location, change.key, change.new)
