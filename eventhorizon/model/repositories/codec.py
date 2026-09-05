"""model/repositories/codec.py — JSON 编解码工具（供本层内部复用，不是端口）。

标准库 sqlite3 不引入 ORM，序列化/反序列化显式写在这里，便于 Event Sourcing
逐条重放时精确控制（README 3 技术选型）。Result / Predicate 的 JSON 判别字段
（"kind" / "type"）与 model/services/event_validation.py 的录入原始格式保持
一致，编辑器草稿、LLM 产出、SQLite 落盘三处读同一套字典结构。
"""
from __future__ import annotations

from typing import Any

from model.domain.agent import Agent, AgentEventHistory, Biography, BiographyEntry, PendingScenario
from model.domain.balance import DEFAULT_REALM_ORDER
from model.domain.cause import CauseLink
from model.domain.diff import AppliedDiff, LocationAttrChange, WorldDiff
from model.domain.events import EventVariant, GameEventDef, GameEventOccurrence, ReplyOption, TriggerSource
from model.domain.items import Inventory
from model.domain.map import Location, LocationCondition, LocationKind, Route, WorldState
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
from model.domain.states import state_by_name
from model.domain.time import AgentTimeAnchor, Epoch, GameTime

# ---------- GameTime ----------


def game_time_to_dict(t: GameTime) -> dict:
    return {"epoch": t.epoch.value, "year": t.year, "month": t.month, "day": t.day, "shichen": t.shichen}


def game_time_from_dict(d: dict) -> GameTime:
    return GameTime.new(Epoch(d["epoch"]), d["year"], d["month"], d["day"], d["shichen"])


# ---------- Predicate / PredicateGroup ----------


def predicate_to_dict(p) -> dict:
    if isinstance(p, PredicateGroup):
        return {"op": p.op, "items": [predicate_to_dict(i) for i in p.items]}
    return {"type": p.type.value, "args": list(p.args)}


def predicate_from_dict(d: dict | None):
    if d is None:
        return None
    if "op" in d:
        return PredicateGroup(op=d["op"], items=tuple(predicate_from_dict(i) for i in d["items"]))
    return Predicate(type=PredicateType(d["type"]), args=tuple(d["args"]))


# ---------- Result union (判别字段 "kind"，与 event_validation.py 的录入格式一致) ----------


def result_to_dict(r) -> dict:
    if isinstance(r, ItemDrop):
        return {"kind": "item_drop", "item_id": r.item_id, "n": r.n}
    if isinstance(r, ItemConsume):
        return {"kind": "item_consume", "item_id": r.item_id, "n": r.n}
    if isinstance(r, StateChange):
        return {"kind": "state_change", "field": r.field, "delta": r.delta, "set_to": r.set_to}
    if isinstance(r, Check):
        return {
            "kind": "check",
            "check_kind": r.kind,
            "on_success": [result_to_dict(x) for x in r.on_success],
            "on_fail": [result_to_dict(x) for x in r.on_fail],
        }
    if isinstance(r, WriteCause):
        return {"kind": "write_cause", "tag": r.tag, "target": r.target, "expires_years": r.expires_years}
    if isinstance(r, ChainEvent):
        return {"kind": "chain_event", "event_id": r.event_id, "source_override": r.source_override.value}
    if isinstance(r, StartScenario):
        return {"kind": "start_scenario", "scenario_id": r.scenario_id}
    if isinstance(r, FlagSet):
        return {"kind": "flag_set", "name": r.name}
    if isinstance(r, FlagClear):
        return {"kind": "flag_clear", "name": r.name}
    raise TypeError(f"unknown Result type: {r!r}")


def result_from_dict(d: dict):
    kind = d["kind"]
    if kind == "item_drop":
        return ItemDrop(item_id=d["item_id"], n=d.get("n", 1))
    if kind == "item_consume":
        return ItemConsume(item_id=d["item_id"], n=d.get("n", 1))
    if kind == "state_change":
        return StateChange(field=d["field"], delta=d.get("delta"), set_to=d.get("set_to"))
    if kind == "check":
        return Check(
            kind=d["check_kind"],
            on_success=tuple(result_from_dict(x) for x in d.get("on_success", ())),
            on_fail=tuple(result_from_dict(x) for x in d.get("on_fail", ())),
        )
    if kind == "write_cause":
        return WriteCause(tag=d["tag"], target=d["target"], expires_years=d.get("expires_years"))
    if kind == "chain_event":
        return ChainEvent(event_id=d["event_id"], source_override=TriggerSource(d.get("source_override", "chain")))
    if kind == "start_scenario":
        return StartScenario(scenario_id=d["scenario_id"])
    if kind == "flag_set":
        return FlagSet(name=d["name"])
    if kind == "flag_clear":
        return FlagClear(name=d["name"])
    raise ValueError(f"unknown result kind: {kind!r}")


# ---------- GameEventDef / GameEventOccurrence ----------


def event_def_to_dict(e: GameEventDef) -> dict:
    return {
        "event_id": e.event_id,
        "applicable_locations": list(e.applicable_locations),
        "applicable_time": list(e.applicable_time) if e.applicable_time is not None else None,
        "predicate": predicate_to_dict(e.predicate) if e.predicate is not None else None,
        "weight": e.weight,
        "duration_shichen": e.duration_shichen,
        "cooldown_shichen": e.cooldown_shichen,
        "max_trigger_per_agent": e.max_trigger_per_agent,
        "exclusive_tags": list(e.exclusive_tags),
        "priority": e.priority,
        "tags": list(e.tags),
        "aliases": list(e.aliases),
        "result_pool": [result_to_dict(r) for r in e.result_pool],
        "variants": [{"text": v.text, "weight": v.weight} for v in e.variants],
        "reply_options": [
            {
                "aliases": list(ro.aliases),
                "results": [result_to_dict(r) for r in ro.results],
                "chain_event_id": ro.chain_event_id,
                "response_text": ro.response_text,
            }
            for ro in e.reply_options
        ],
        "novelty_curve_override": e.novelty_curve_override,
        "scenario_ref": e.scenario_ref,
        "schema_version": e.schema_version,
        "is_draft": e.is_draft,
        "is_command": e.is_command,
        "predicate_text": e.predicate_text,
        "predicate_embedding": list(e.predicate_embedding),
        "result_text": e.result_text,
    }


def event_def_from_dict(d: dict) -> GameEventDef:
    return GameEventDef(
        event_id=d["event_id"],
        applicable_locations=tuple(d.get("applicable_locations", ("*",))),
        applicable_time=tuple(d["applicable_time"]) if d.get("applicable_time") is not None else None,
        predicate=predicate_from_dict(d.get("predicate")),
        weight=d.get("weight", 1.0),
        duration_shichen=d.get("duration_shichen", 1),
        cooldown_shichen=d.get("cooldown_shichen", 0),
        max_trigger_per_agent=d.get("max_trigger_per_agent"),
        exclusive_tags=tuple(d.get("exclusive_tags", ())),
        priority=d.get("priority", 5),
        tags=tuple(d.get("tags", ())),
        aliases=tuple(d.get("aliases", ())),
        result_pool=tuple(result_from_dict(r) for r in d.get("result_pool", ())),
        variants=tuple(EventVariant(text=v["text"], weight=v.get("weight", 1.0)) for v in d.get("variants", ())),
        reply_options=tuple(
            ReplyOption(
                aliases=tuple(ro["aliases"]),
                results=tuple(result_from_dict(r) for r in ro.get("results", ())),
                chain_event_id=ro.get("chain_event_id"),
                response_text=ro.get("response_text", ""),
            )
            for ro in d.get("reply_options", ())
        ),
        novelty_curve_override=d.get("novelty_curve_override"),
        scenario_ref=d.get("scenario_ref"),
        schema_version=d.get("schema_version", 1),
        is_draft=d.get("is_draft", False),
        is_command=d.get("is_command", False),
        predicate_text=d.get("predicate_text", ""),
        predicate_embedding=tuple(d.get("predicate_embedding") or ()),
        result_text=d.get("result_text", ""),
    )


def applied_diff_to_dict(diff: AppliedDiff | None) -> dict | None:
    if diff is None:
        return None
    pending_scenario = diff.pending_scenario_set
    if pending_scenario == "__unset__":
        pending_scenario_json: Any = "__unset__"
    elif pending_scenario is None:
        pending_scenario_json = None
    else:
        pending_scenario_json = {
            "scenario_id": pending_scenario.scenario_id,
            "current_node_id": pending_scenario.current_node_id,
            "host_event_id": pending_scenario.host_event_id,
        }
    return {
        "attr_deltas": [list(x) for x in diff.attr_deltas],
        "realm_set": diff.realm_set,
        "location_set": diff.location_set,
        "location_type_set": diff.location_type_set,
        "items_add": [list(x) for x in diff.items_add],
        "items_remove": [list(x) for x in diff.items_remove],
        "flags_set": list(diff.flags_set),
        "flags_clear": list(diff.flags_clear),
        "causes_add": [cause_link_to_dict(c) for c in diff.causes_add],
        "time_shichen_delta": diff.time_shichen_delta,
        "scene_focus_set": diff.scene_focus_set,
        "pending_encounter_set": diff.pending_encounter_set,
        "pending_scenario_set": pending_scenario_json,
        "state_set": diff.state_set,
        "pending_retreat_prompt_set": diff.pending_retreat_prompt_set,
    }


def applied_diff_from_dict(d: dict | None) -> AppliedDiff | None:
    if d is None:
        return None
    pending_scenario_json = d.get("pending_scenario_set", "__unset__")
    if pending_scenario_json == "__unset__":
        pending_scenario: Any = "__unset__"
    elif pending_scenario_json is None:
        pending_scenario = None
    else:
        pending_scenario = PendingScenario(**pending_scenario_json)
    return AppliedDiff(
        attr_deltas=tuple(tuple(x) for x in d.get("attr_deltas", ())),
        realm_set=d.get("realm_set"),
        location_set=d.get("location_set"),
        location_type_set=d.get("location_type_set"),
        items_add=tuple(tuple(x) for x in d.get("items_add", ())),
        items_remove=tuple(tuple(x) for x in d.get("items_remove", ())),
        flags_set=tuple(d.get("flags_set", ())),
        flags_clear=tuple(d.get("flags_clear", ())),
        causes_add=tuple(cause_link_from_dict(c) for c in d.get("causes_add", ())),
        time_shichen_delta=d.get("time_shichen_delta", 0),
        scene_focus_set=d.get("scene_focus_set"),
        pending_encounter_set=d.get("pending_encounter_set"),
        pending_scenario_set=pending_scenario,
        state_set=d.get("state_set"),
        pending_retreat_prompt_set=d.get("pending_retreat_prompt_set"),
    )


def world_diff_to_dict(diff: WorldDiff | None) -> dict | None:
    if diff is None:
        return None
    return {
        "location_changes": [
            {"location_id": c.location_id, "key": c.key, "old": c.old, "new": c.new} for c in diff.location_changes
        ]
    }


def world_diff_from_dict(d: dict | None) -> WorldDiff | None:
    if d is None:
        return None
    return WorldDiff(
        location_changes=tuple(
            LocationAttrChange(c["location_id"], c["key"], c["old"], c["new"]) for c in d.get("location_changes", ())
        )
    )


def cause_link_to_dict(c: CauseLink) -> dict:
    return {
        "actor": c.actor,
        "action": c.action,
        "target": c.target,
        "tag": c.tag,
        "expires_at": game_time_to_dict(c.expires_at) if c.expires_at is not None else None,
    }


def cause_link_from_dict(d: dict) -> CauseLink:
    return CauseLink(
        actor=d["actor"],
        action=d["action"],
        target=d["target"],
        tag=d["tag"],
        expires_at=game_time_from_dict(d["expires_at"]) if d.get("expires_at") is not None else None,
    )


def occurrence_to_dict(occ: GameEventOccurrence) -> dict:
    return {
        "event_id": occ.event_id,
        "trigger_source": occ.trigger_source.value,
        "agent_id": occ.agent_id,
        "occurred_at": game_time_to_dict(occ.occurred_at),
        "chosen_variant_index": occ.chosen_variant_index,
        "applied_diff": applied_diff_to_dict(occ.applied_diff),
        "world_diff": world_diff_to_dict(occ.world_diff),
        "def_schema_version": occ.def_schema_version,
    }


def occurrence_from_dict(d: dict) -> GameEventOccurrence:
    return GameEventOccurrence(
        event_id=d["event_id"],
        trigger_source=TriggerSource(d["trigger_source"]),
        agent_id=d["agent_id"],
        occurred_at=game_time_from_dict(d["occurred_at"]),
        chosen_variant_index=d.get("chosen_variant_index", 0),
        applied_diff=applied_diff_from_dict(d.get("applied_diff")),
        world_diff=world_diff_from_dict(d.get("world_diff")),
        def_schema_version=d.get("def_schema_version", 1),
    )


# ---------- Agent（含挂起字段与 AgentEventHistory，读档丢一个都会露馅） ----------


def agent_to_dict(agent: Agent) -> dict:
    pending_scenario = None
    if agent.pending_scenario is not None:
        pending_scenario = {
            "scenario_id": agent.pending_scenario.scenario_id,
            "current_node_id": agent.pending_scenario.current_node_id,
            "host_event_id": agent.pending_scenario.host_event_id,
        }
    history = agent.event_history
    return {
        "agent_id": agent.agent_id,
        "location_id": agent.location_id,
        "location_type": agent.location_type,
        "age": agent.age,
        "realm": agent.realm,
        "money": agent.money,
        "satiety": agent.satiety,
        "cultivation": agent.cultivation,
        "heart_demon": agent.heart_demon,
        "lifespan_left": agent.lifespan_left,
        "flags": list(agent.flags),
        "inventory": dict(agent.inventory.counts),
        "time_anchor": {
            "last_synced_game_time": game_time_to_dict(agent.time_anchor.last_synced_game_time),
            "pending_duration_shichen": agent.time_anchor.pending_duration_shichen,
        },
        "event_history": {
            "triggers": {k: [game_time_to_dict(t) for t in v] for k, v in history.triggers.items()},
            "variant_cursor": dict(history.variant_cursor),
            "recent_tags": [[tag, game_time_to_dict(t)] for tag, t in history.recent_tags],
            "exclusive_tag_expiry": {k: game_time_to_dict(v) for k, v in history.exclusive_tag_expiry.items()},
            "last_trigger_seq": dict(history.last_trigger_seq),
            "sequence": history._sequence,
        },
        "state": agent.state.name,
        "causes": [cause_link_to_dict(c) for c in agent.causes],
        "pending_encounter_id": agent.pending_encounter_id,
        "pending_scenario": pending_scenario,
        "scene_focus": agent.scene_focus,
        "spirit_root": agent.spirit_root,
        "aptitude": agent.aptitude,
        "luck": agent.luck,
        "insight": agent.insight,
        "origin": agent.origin,
        "turn_count": agent.turn_count,
        "pending_retreat_prompt": agent.pending_retreat_prompt,
        "consecutive_breakthrough_failures": agent.consecutive_breakthrough_failures,
    }


def agent_from_dict(d: dict) -> Agent:
    history_d = d.get("event_history", {})
    history = AgentEventHistory(
        triggers={k: [game_time_from_dict(t) for t in v] for k, v in history_d.get("triggers", {}).items()},
        variant_cursor=dict(history_d.get("variant_cursor", {})),
        recent_tags=[(tag, game_time_from_dict(t)) for tag, t in history_d.get("recent_tags", [])],
        exclusive_tag_expiry={k: game_time_from_dict(v) for k, v in history_d.get("exclusive_tag_expiry", {}).items()},
        last_trigger_seq=dict(history_d.get("last_trigger_seq", {})),
    )
    history._sequence = history_d.get("sequence", 0)

    pending_scenario = None
    if d.get("pending_scenario") is not None:
        pending_scenario = PendingScenario(**d["pending_scenario"])

    time_anchor_d = d["time_anchor"]
    return Agent(
        agent_id=d["agent_id"],
        location_id=d["location_id"],
        location_type=d["location_type"],
        age=d["age"],
        realm=d.get("realm", DEFAULT_REALM_ORDER[0]),
        money=d.get("money", 0),
        satiety=d.get("satiety", 100),
        cultivation=d.get("cultivation", 0.0),
        heart_demon=d.get("heart_demon", 0.0),
        lifespan_left=d.get("lifespan_left", 80.0),
        flags=set(d.get("flags", ())),
        inventory=Inventory(counts=dict(d.get("inventory", {}))),
        time_anchor=AgentTimeAnchor(
            last_synced_game_time=game_time_from_dict(time_anchor_d["last_synced_game_time"]),
            pending_duration_shichen=time_anchor_d.get("pending_duration_shichen", 0),
        ),
        event_history=history,
        state=state_by_name(d.get("state", "idle")),
        causes=[cause_link_from_dict(c) for c in d.get("causes", ())],
        pending_encounter_id=d.get("pending_encounter_id"),
        pending_scenario=pending_scenario,
        scene_focus=d.get("scene_focus"),
        spirit_root=d.get("spirit_root", ""),
        aptitude=d.get("aptitude", 1.0),
        luck=d.get("luck", 0.0),
        insight=d.get("insight", 0.0),
        origin=d.get("origin", ""),
        turn_count=d.get("turn_count", 0),
        pending_retreat_prompt=d.get("pending_retreat_prompt", False),
        consecutive_breakthrough_failures=d.get("consecutive_breakthrough_failures", 0),
    )


# ---------- WorldState（地图快照，供地图回滚 §3.3.1 复用同一份 WorldDiff.invert）----------


def location_to_dict(loc: Location) -> dict:
    return {
        "location_id": loc.location_id,
        "name": loc.name,
        "kind": loc.kind.value,
        "location_type": loc.location_type,
        "x": loc.x,
        "y": loc.y,
        "qi_density": loc.qi_density,
        "danger_level": loc.danger_level,
        "condition": loc.condition.value,
        "parent_location_id": loc.parent_location_id,
        "hidden": loc.hidden,
        "concealment": loc.concealment,
        "discovered": loc.discovered,
    }


def location_from_dict(d: dict) -> Location:
    return Location(
        location_id=d["location_id"],
        name=d["name"],
        kind=LocationKind(d["kind"]),
        location_type=d["location_type"],
        x=d.get("x", 0.0),
        y=d.get("y", 0.0),
        qi_density=d.get("qi_density", 1.0),
        danger_level=d.get("danger_level", 0.0),
        condition=LocationCondition(d.get("condition", LocationCondition.INTACT.value)),
        parent_location_id=d.get("parent_location_id"),
        hidden=d.get("hidden", False),
        concealment=d.get("concealment", 0.0),
        discovered=d.get("discovered", False),
    )


def route_to_dict(r: Route) -> dict:
    return {"from_id": r.from_id, "to_id": r.to_id, "move_cost_shichen": r.move_cost_shichen, "bidirectional": r.bidirectional}


def route_from_dict(d: dict) -> Route:
    return Route(
        from_id=d["from_id"],
        to_id=d["to_id"],
        move_cost_shichen=d.get("move_cost_shichen", 1),
        bidirectional=d.get("bidirectional", True),
    )


def world_state_to_dict(world: WorldState) -> dict:
    return {
        "locations": {lid: location_to_dict(loc) for lid, loc in world.locations.items()},
        "routes": [route_to_dict(r) for r in world.routes],
        "weather": world.weather,
    }


def world_state_from_dict(d: dict) -> WorldState:
    return WorldState(
        locations={lid: location_from_dict(loc) for lid, loc in d.get("locations", {}).items()},
        routes=[route_from_dict(r) for r in d.get("routes", ())],
        weather=d.get("weather", "晴"),
    )


def biography_to_dict(bio: Biography) -> dict:
    return {"entries": [{"at": game_time_to_dict(e.at), "text": e.text, "event_id": e.event_id} for e in bio.entries]}


def biography_from_dict(d: dict) -> Biography:
    return Biography(
        entries=[
            BiographyEntry(at=game_time_from_dict(e["at"]), text=e["text"], event_id=e.get("event_id"))
            for e in d.get("entries", ())
        ]
    )
