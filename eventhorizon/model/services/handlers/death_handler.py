"""model/services/handlers/death_handler.py — 死亡结算（对应 README §3.8）。

薄适配器：真正的业务逻辑在 death_service（生平碑文、清理挂起态、三选一重玩）。
DeathEvent 走总线是为了让其它订阅者（UI、日程）也能感知死亡。重玩改写的是同一
agent_id 上的状态，不是换主角、也不是重放存档，所以重玩本身不经总线（README §2）。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from model.domain.system_events import DeathEvent
    from model.services.death_service import DeathService
    from model.services.ports import AgentRepository


class DeathHandler:
    def __init__(self, death_service: "DeathService", agents: "AgentRepository") -> None:
        self._death_service = death_service
        self._agents = agents

    def handle(self, event: "DeathEvent") -> None:
        agent = self._agents.load(event.agent_id)
        if agent.state.name == "dead":
            return
        self._death_service.handle_death(agent, event.at, event.cause)
        self._agents.save(agent)
