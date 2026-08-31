"""model/services/death_service.py — 死亡结算与转世/夺舍/继承（对应 README 2.5 /
4.13，GAME_DESIGN §8）。

重玩换的是主角 id，不是重放存档，故不经总线，单独用例；reincarnate/possess/
inherit 直接构造或改写 Agent，不走 apply_agent_diff——这是文档明确标注的例外
（"单独用例"），不是常规对局路径的一部分。
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from model.domain.agent import AgentEventHistory, PendingScenario
from model.domain.items import Inventory
from model.domain.states import DeadState, IdleState
from model.domain.time import AgentTimeAnchor

if TYPE_CHECKING:
    from model.domain.agent import Agent
    from model.domain.balance import BalanceTable
    from model.domain.time import GameTime

_POSSESS_MIN_REALM = "金丹"  # GAME_DESIGN §8.2："夺舍（需金丹以上）"


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
    """§8.2："未达条件的选项在文案里说明原因而非隐藏"——保留信息透明度。"""

    path: RebirthPath
    available: bool
    reason: str


class DeathService:
    """结算 Biography 碑文 → 清日程与在世标记（关系转"亡故"不删除）→ 亲友报仇/守孝
    事件（V1 接入关系网后启用）→ 重玩三选一。"""

    def __init__(self, biography_provider=None) -> None:
        self._biography_provider = biography_provider  # agent_id -> Biography，可选

    def handle_death(self, agent: "Agent", at: "GameTime", cause: str) -> DeathOutcome:
        agent.state = DeadState()
        agent.pending_encounter_id = None
        agent.pending_scenario = None
        biography = self._biography_provider(agent.agent_id) if self._biography_provider else None
        if biography is not None and biography.entries:
            epitaph = f"{agent.agent_id}，{biography.epitaph()}"
        else:
            epitaph = compose_epitaph(agent, at, cause)
        # V1：遍历 agent.causes 把关系网中的"在世"标记转"亡故"、触发亲友报仇/守孝事件，
        # 留待接入关系网存储后实现（本底座 CauseLink 只记标签，不持有关系网索引）。
        return DeathOutcome(epitaph=epitaph, cause=cause)

    def available_rebirth_paths(self, agent: "Agent", balance: "BalanceTable") -> list[RebirthPathOption]:
        """§8.2 三选一，各自附体验设计意图（§8.3）与是否可选的原因。"""
        can_possess = False
        if agent.realm in balance.realm_order and _POSSESS_MIN_REALM in balance.realm_order:
            can_possess = balance.realm_rank(agent.realm) >= balance.realm_rank(_POSSESS_MIN_REALM)
        return [
            RebirthPathOption(
                RebirthPath.REINCARNATE, True, "以凡人之身重新开始，带走部分资质与悟性，仇人可能寻上门。"
            ),
            RebirthPathOption(
                RebirthPath.POSSESS,
                can_possess,
                "残魂夺取他人躯壳，境界降一级，心魔大增。" if can_possess else f"境界不足（需 {_POSSESS_MIN_REALM} 以上），暂不可选。",
            ),
            RebirthPathOption(RebirthPath.INHERIT, True, "让一位后辈接过衣钵，继承部分资源。"),
        ]

    def reincarnate(self, dead_agent: "Agent", new_agent_id: str, keep_cause_tags: tuple[str, ...] = ()) -> "Agent":
        """转世：保留部分资质/悟性，重置境界与寿元，以凡人身份重新开始；
        可继承部分未过期 CauseLink（仇人可能寻上门）。"""
        from model.domain.agent import Agent
        from model.domain.balance import DEFAULT_REALM_ORDER

        inherited_causes = [c for c in dead_agent.causes if c.tag in keep_cause_tags]
        return Agent(
            agent_id=new_agent_id,
            location_id=dead_agent.location_id,
            location_type=dead_agent.location_type,
            age=0,
            realm=DEFAULT_REALM_ORDER[0],
            money=0,
            satiety=100,
            cultivation=0.0,
            heart_demon=0.0,
            lifespan_left=80.0,
            flags=set(),
            inventory=Inventory(),
            time_anchor=AgentTimeAnchor(last_synced_game_time=dead_agent.time_anchor.current_game_time),
            event_history=AgentEventHistory(),
            state=IdleState(),
            causes=inherited_causes,
        )

    def possess(self, dead_agent: "Agent", host_npc: "Agent") -> "Agent":
        """夺舍：金丹以上境界可选，以残魂状态夺取一名 NPC 躯体，继承其身份与社交关系，
        但境界下降一级、心魔大增。"""
        from model.domain.balance import DEFAULT_REALM_ORDER

        rank = DEFAULT_REALM_ORDER.index(host_npc.realm) if host_npc.realm in DEFAULT_REALM_ORDER else 0
        host_npc.realm = DEFAULT_REALM_ORDER[max(0, rank - 1)]
        host_npc.heart_demon += 0.3  # 心魔大增（GAME_DESIGN §7.2 用的是 0..1 量级的小数刻度）
        host_npc.state = IdleState()
        return host_npc

    def inherit(self, dead_agent: "Agent", heir: "Agent", keep_cause_tags: tuple[str, ...] = ()) -> "Agent":
        """继承：选择一名已存在的弟子/后代角色继续游戏，继承部分资源与未过期
        CauseLink，不继承"未完成主线"（本引擎本无主线）。"""
        heir.money += dead_agent.money // 2
        heir.causes.extend(c for c in dead_agent.causes if c.tag in keep_cause_tags)
        heir.state = IdleState()
        return heir


def compose_epitaph(agent: "Agent", at: "GameTime", cause: str) -> str:
    """§8.1：碑文由关键事件流自动摘要（因果标签最重的 2~3 条 + 最高境界 + 享年），
    不需要人工撰写模板内容。示例：王小二，太乙历一百八十年卒，享年八十。一生历经
    三次突破，两位知己，一段未竟的仇。"""
    heavy_tags = _heaviest_cause_tags(agent.causes, at, limit=3)
    tag_clauses = [f"{count}位{tag}" if count > 1 else f"一段{tag}" for tag, count in heavy_tags]
    breakthrough_attempts = agent.event_history.trigger_count("breakthrough")

    achievements = [f"一生修至{agent.realm}"]
    if breakthrough_attempts:
        achievements.append(f"历经{breakthrough_attempts}次突破")
    achievements.extend(tag_clauses)

    return (
        f"{agent.agent_id}，太乙历{at.year}年卒，享年{agent.age}。"
        f"{'，'.join(achievements)}。"
    )


def _heaviest_cause_tags(causes: list, at: "GameTime", limit: int = 3) -> list[tuple[str, int]]:
    counts = Counter(c.tag for c in causes if not c.is_expired(at))
    return counts.most_common(limit)
