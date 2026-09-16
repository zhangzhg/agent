"""content/session.py — 玩家主角的初始状态（太乙历一百年，苍梧城，六岁）。

正式开局经 CharacterService 建角；本函数只负责把一个新 Agent 写进仓库。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bootstrap import AppContext
    from model.domain.agent import Agent
    from model.domain.map import WorldState
    from model.services.clock_service import GameClock
    from model.services.ports import AgentRepository


def spawn_player_agent(
    agent_repo: "AgentRepository",
    world: "WorldState",
    clock: "GameClock",
    agent_id: str,
) -> "Agent":
    """已存在则原样返回；否则新建默认主角。"""
    try:
        return agent_repo.load(agent_id)
    except LookupError:
        pass

    from content.map import DEFAULT_SPAWN_LOCATION_ID
    from model.domain.agent import Agent, AgentEventHistory
    from model.domain.balance import DEFAULT_REALM_ORDER
    from model.domain.items import Inventory
    from model.domain.states import IdleState
    from model.domain.time import AgentTimeAnchor

    spawn = world.locations.get(DEFAULT_SPAWN_LOCATION_ID)
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
        time_anchor=AgentTimeAnchor(last_synced_game_time=clock.now()),
        event_history=AgentEventHistory(),
        state=IdleState(),
        causes=[],
    )
    agent_repo.save(agent)
    return agent


def create_player_agent(app: "AppContext", agent_id: str) -> "Agent":
    return spawn_player_agent(app.agent_repo, app.world, app.clock, agent_id)


def ensure_seed_agent(app: "AppContext", agent_id: str) -> "Agent":
    """测试/日程接线用：没有就建一个，不经过验证码。正式入口走 CharacterService。"""
    return create_player_agent(app, agent_id)
