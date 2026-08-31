"""model/domain/states.py — Agent 状态机（状态模式，对应 README 3.3）。

顺序（硬约束）：仲裁通过 → predicate.evaluate → try_transition → 跑结果池产 diff →
apply → settle() 定落点。谓词失败则状态不变、不产 diff、不写日志。

状态类不持有 EventBus。PlayTurnService 在转换成功后 publish(AgentStateChanged)。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from model.domain.agent import Agent
    from model.domain.events import GameEventOccurrence


class AgentState(ABC):
    name: str

    @abstractmethod
    def try_transition(self, agent: "Agent", incoming: "GameEventOccurrence") -> "AgentState | None":
        """返回新状态则转换成功；返回 None 则拒绝（非法指令在此拦，不散落在 Handler 里）。"""

    def settle(self, agent: "Agent") -> "AgentState":
        """结算收尾的落点：本轮跑完后由 PlayTurn 调用，决定回 Idle 还是进挂起态。
        禁止在 PlayTurn 里直接 `agent.state = IdleState()`——那样绕开了状态机，
        "状态切换必须经状态对象"（README 3.3）就成了空话。"""
        if agent.pending_scenario is not None:
            return ScenarioPendingState()
        if agent.pending_encounter_id is not None:
            return EncounterPendingState()
        return IdleState()


class IdleState(AgentState):
    name = "idle"

    def try_transition(self, agent, incoming):
        from model.domain.events import TriggerSource

        # CHAIN 必须能从 idle 接受：主流程（execute_occurrence / _resolve_reply_option）
        # 都是先 settle() 回 idle，再执行/发布 ctx.spawned 里的连锁事件——如果 idle 不
        # 接 CHAIN，任何链式事件到这一步就会被 try_transition 拒掉，diff 压根不会产生。
        # 这是原设计的一个真实缺口，不是新引入的口子。
        if incoming.trigger_source in (
            TriggerSource.PLAYER, TriggerSource.SCHEDULE, TriggerSource.FORCE,
            TriggerSource.ENCOUNTER, TriggerSource.CHAIN,
        ):
            return ActingState()
        return None


class ActingState(AgentState):
    name = "acting"

    def try_transition(self, agent, incoming):
        from model.domain.events import TriggerSource

        if incoming.trigger_source == TriggerSource.FORCE:
            return ActingState()  # 打断后仍在行动中结算强制事件
        if incoming.trigger_source == TriggerSource.PLAYER:
            return ActingState()  # 抢占：新命令替换当前主行为（旧行为由 PlayTurn 丢弃/入队）
        return None  # ENCOUNTER 在 acting 时不转换，由 PlayTurn 决定挂起或同回合叙述


class ClosedDoorState(AgentState):
    name = "closed_door"

    def try_transition(self, agent, incoming):
        from model.domain.events import TriggerSource

        if incoming.trigger_source == TriggerSource.FORCE:
            return ActingState()
        return None


class EncounterPendingState(AgentState):
    name = "encounter_pending"

    def try_transition(self, agent, incoming):
        from model.domain.events import TriggerSource

        if incoming.trigger_source in (TriggerSource.PLAYER, TriggerSource.FORCE, TriggerSource.CHAIN):
            return ActingState()
        return None


class ScenarioPendingState(AgentState):
    """流程图执行中，等玩家下一句选边。与 EncounterPending 的区别：
    挂起的是 pending_scenario（图内节点），不是一条待接受的奇遇。"""

    name = "scenario_pending"

    def try_transition(self, agent, incoming):
        from model.domain.events import TriggerSource

        if incoming.trigger_source in (TriggerSource.PLAYER, TriggerSource.FORCE, TriggerSource.CHAIN):
            return ActingState()
        return None


class DeadState(AgentState):
    name = "dead"

    def try_transition(self, agent, incoming):
        return None

    def settle(self, agent):
        return self  # 死亡是吸收态，只由 death_service 的重玩流程换人


_STATES_BY_NAME: dict[str, type[AgentState]] = {
    IdleState.name: IdleState,
    ActingState.name: ActingState,
    ClosedDoorState.name: ClosedDoorState,
    EncounterPendingState.name: EncounterPendingState,
    ScenarioPendingState.name: ScenarioPendingState,
    DeadState.name: DeadState,
}


def state_by_name(name: str) -> AgentState:
    """按名字还原状态对象，供快照读档 / diff.state_set 重放使用。"""
    cls = _STATES_BY_NAME.get(name)
    if cls is None:
        raise ValueError(f"unknown agent state name: {name!r}")
    return cls()
