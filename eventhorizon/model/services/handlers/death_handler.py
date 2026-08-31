"""model/services/handlers/death_handler.py — 死亡走 2.5 结算（对应 README 3.2）。

薄适配器：真正的业务逻辑在 death_service（生平碑文、清理日程/关系、亲友反应、
三选一重玩入口）。DeathEvent 走总线是为了让其它订阅者（UI、日程）也能感知死亡，
但重玩换的是主角 id，不是重放存档，所以重玩本身不经总线，是单独用例（README 4.13）。
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
        self._death_service.handle_death(agent, event.at, event.cause)
        self._agents.save(agent)
