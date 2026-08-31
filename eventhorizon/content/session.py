"""content/session.py — 演示用的默认主角创建（GAME_DESIGN §1.1 / README 2.2.1）。

CLI 入口和 Web 入口都要"首次访问时给一个默认主角"，抽成共用函数避免两处各写
一份、悄悄漂移。不代表真正的角色创建流程——那是录入/新建游戏页面的职责。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bootstrap import AppContext
    from model.domain.agent import Agent


def ensure_seed_agent(app: "AppContext", agent_id: str) -> "Agent":
    """已存在则原样返回；否则新建一个"太乙历一百年，苍梧城，六岁"的默认主角。"""
    try:
        return app.agent_repo.load(agent_id)
    except LookupError:
        pass

    from content.map import DEFAULT_SPAWN_LOCATION_ID
    from model.domain.agent import Agent, AgentEventHistory
    from model.domain.balance import DEFAULT_REALM_ORDER
    from model.domain.items import Inventory
    from model.domain.states import IdleState
    from model.domain.time import AgentTimeAnchor

    spawn = app.world.locations.get(DEFAULT_SPAWN_LOCATION_ID)
    agent = Agent(
        agent_id=agent_id,
        location_id=DEFAULT_SPAWN_LOCATION_ID if spawn else "某城",
        location_type=spawn.location_type if spawn else "城市",
        age=6,
        realm=DEFAULT_REALM_ORDER[0],
        money=10,
        satiety=80,
        cultivation=0.0,
        heart_demon=0.0,
        lifespan_left=80.0,
        flags=set(),
        inventory=Inventory(),
        time_anchor=AgentTimeAnchor(last_synced_game_time=app.clock.now()),
        event_history=AgentEventHistory(),
        state=IdleState(),
        causes=[],
    )
    app.agent_repo.save(agent)
    return agent
