"""model/services/death_service.py — 死亡结算与转世/夺舍/继承（对应 README 2.5）。

重玩换的是同一存档主角的状态，不是重放存档，故不经总线，单独用例；reincarnate/
possess/inherit 直接改写 Agent，不走 apply_agent_diff——这是文档明确标注的例外
（"单独用例"），不是常规对局路径的一部分。
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from model.domain.agent import AgentEventHistory
from model.domain.items import Inventory
from model.domain.states import DeadState, IdleState

if TYPE_CHECKING:
    from model.domain.agent import Agent
    from model.domain.balance import BalanceTable
    from model.domain.time import GameTime

_POSSESS_MIN_REALM = "金丹"
_KEEP_CAUSE_TAGS = ("仇恨", "拜师")


class RebirthPath(str, Enum):
    REINCARNATE = "转世"
    POSSESS = "夺舍"
    INHERIT = "继承"


@dataclass
class DeathOutcome:
    epitaph: str
    cause: str


@dataclass
class RebirthPathOption:
    path: RebirthPath
    available: bool
    reason: str


class DeathService:
    def __init__(self, biography_provider=None) -> None:
        self._biography_provider = biography_provider

    def handle_death(self, agent: "Agent", at: "GameTime", cause: str) -> DeathOutcome:
        agent.state = DeadState()
        agent.pending_encounter_id = None
        agent.pending_scenario = None
        agent.pending_clarification = None
        agent.pending_live_result = None
        agent.pending_retreat_prompt = False
        if agent.lifespan_left < 0:
            agent.lifespan_left = 0.0
        biography = self._biography_provider(agent.agent_id) if self._biography_provider else None
        if biography is not None and biography.entries:
            epitaph = f"{agent.agent_id}，{biography.epitaph()}"
        else:
            epitaph = compose_epitaph(agent, at, cause)
        return DeathOutcome(epitaph=epitaph, cause=cause)

    def available_rebirth_paths(
        self, agent: "Agent", balance: "BalanceTable", hosts: list["Agent"] | None = None
    ) -> list[RebirthPathOption]:
        hosts = hosts or []
        npcs = [a for a in hosts if a.is_npc and a.agent_id != agent.agent_id]
        can_possess = False
        if agent.realm in balance.realm_order and _POSSESS_MIN_REALM in balance.realm_order:
            can_possess = balance.realm_rank(agent.realm) >= balance.realm_rank(_POSSESS_MIN_REALM)
        possess_reason = "残魂夺取他人躯壳，境界降一级，心魔大增。"
        if not can_possess:
            possess_reason = f"境界不足（需 {_POSSESS_MIN_REALM} 以上），暂不可选。"
        elif not npcs:
            possess_reason = "附近没有可以夺舍的躯壳。"
            can_possess = False
        inherit_ok = bool(npcs)
        inherit_reason = "让一位后辈接过衣钵，继承部分资源。" if inherit_ok else "尚无可以继承的弟子或后辈。"
        return [
            RebirthPathOption(
                RebirthPath.REINCARNATE, True, "以凡人之身重新开始，带走部分资质与悟性，仇人可能寻上门。"
            ),
            RebirthPathOption(RebirthPath.POSSESS, can_possess, possess_reason),
            RebirthPathOption(RebirthPath.INHERIT, inherit_ok, inherit_reason),
        ]

    def reincarnate(self, agent: "Agent", keep_cause_tags: tuple[str, ...] = _KEEP_CAUSE_TAGS) -> "Agent":
        """转世：同一 agent_id 上重置境界/寿元/年龄，保留部分资质、悟性与指定因果。"""
        from model.domain.balance import DEFAULT_REALM_ORDER

        inherited = [c for c in agent.causes if c.tag in keep_cause_tags]
        aptitude = 1.0 + (agent.aptitude - 1.0) * 0.5
        insight = agent.insight * 0.5
        luck = agent.luck * 0.5
        agent.age = 6
        agent.realm = DEFAULT_REALM_ORDER[0]
        agent.money = 10
        agent.satiety = 100
        agent.cultivation = 0.0
        agent.heart_demon = 0.0
        agent.lifespan_left = 80.0
        agent.flags = set()
        agent.inventory = Inventory()
        agent.event_history = AgentEventHistory()
        agent.state = IdleState()
        agent.causes = inherited
        agent.aptitude = aptitude
        agent.insight = insight
        agent.luck = luck
        agent.consecutive_breakthrough_failures = 0
        agent.turn_count = 0
        return agent

    def possess(self, dead_agent: "Agent", host_npc: "Agent") -> "Agent":
        """夺舍：同一 agent_id 接管 NPC 的地点与身份，境界降一级、心魔大增。"""
        from model.domain.balance import DEFAULT_REALM_ORDER

        rank = DEFAULT_REALM_ORDER.index(host_npc.realm) if host_npc.realm in DEFAULT_REALM_ORDER else 0
        dead_agent.location_id = host_npc.location_id
        dead_agent.location_type = host_npc.location_type
        dead_agent.realm = DEFAULT_REALM_ORDER[max(0, rank - 1)]
        dead_agent.heart_demon = host_npc.heart_demon + 0.3
        dead_agent.cultivation = 0.0
        dead_agent.age = host_npc.age
        dead_agent.money = host_npc.money
        dead_agent.inventory = host_npc.inventory
        dead_agent.causes = list(host_npc.causes)
        dead_agent.event_history = AgentEventHistory()
        dead_agent.state = IdleState()
        dead_agent.pending_encounter_id = None
        dead_agent.pending_scenario = None
        dead_agent.pending_clarification = None
        dead_agent.pending_live_result = None
        dead_agent.pending_retreat_prompt = False
        dead_agent.lifespan_left = max(dead_agent.lifespan_left, 40.0)
        return dead_agent

    def inherit(self, dead_agent: "Agent", heir: "Agent", keep_cause_tags: tuple[str, ...] = _KEEP_CAUSE_TAGS) -> "Agent":
        """继承：同一 agent_id 换成后辈的地点/境界，继承一半金钱与指定因果。"""
        inherited = [c for c in dead_agent.causes if c.tag in keep_cause_tags]
        money = dead_agent.money // 2 + heir.money
        dead_agent.location_id = heir.location_id
        dead_agent.location_type = heir.location_type
        dead_agent.age = heir.age
        dead_agent.realm = heir.realm
        dead_agent.cultivation = heir.cultivation
        dead_agent.heart_demon = heir.heart_demon
        dead_agent.aptitude = heir.aptitude
        dead_agent.insight = heir.insight
        dead_agent.luck = heir.luck
        dead_agent.money = money
        dead_agent.inventory = heir.inventory
        dead_agent.lifespan_left = heir.lifespan_left
        dead_agent.flags = set(heir.flags)
        dead_agent.causes = list(heir.causes) + inherited
        dead_agent.event_history = AgentEventHistory()
        dead_agent.state = IdleState()
        dead_agent.pending_encounter_id = None
        dead_agent.pending_scenario = None
        dead_agent.pending_clarification = None
        dead_agent.pending_live_result = None
        dead_agent.pending_retreat_prompt = False
        return dead_agent


def compose_epitaph(agent: "Agent", at: "GameTime", cause: str) -> str:
    heavy_tags = _heaviest_cause_tags(agent.causes, at, limit=3)
    tag_clauses = [f"{count}位{tag}" if count > 1 else f"一段{tag}" for tag, count in heavy_tags]
    breakthrough_attempts = agent.event_history.trigger_count("breakthrough")

    achievements = [f"一生修至{agent.realm}"]
    if breakthrough_attempts:
        achievements.append(f"历经{breakthrough_attempts}次突破")
    achievements.extend(tag_clauses)

    return (
        f"{agent.agent_id}，太乙历{at.year}年卒，享年{agent.age}，因{cause}。"
        f"{'，'.join(achievements)}。"
    )


def _heaviest_cause_tags(causes: list, at: "GameTime", limit: int = 3) -> list[tuple[str, int]]:
    counts = Counter(c.tag for c in causes if not c.is_expired(at))
    return counts.most_common(limit)
