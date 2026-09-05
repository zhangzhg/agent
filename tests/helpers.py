"""tests/helpers.py — 测试共用的构造函数。用 unittest（不依赖 pytest，环境里没有
装它）；同一套 helper 若装了 pytest 也能直接跑。
"""
from __future__ import annotations

import random

from model.domain.agent import Agent, AgentEventHistory
from model.domain.balance import BalanceTable, DEFAULT_REALM_ORDER
from model.domain.items import Inventory
from model.domain.map import Location, LocationKind, WorldState, WorldView
from model.domain.states import IdleState
from model.domain.time import AgentTimeAnchor, Epoch, GameTime


def make_time(year=100, month=1, day=1, shichen=6) -> GameTime:
    return GameTime.new(Epoch.TAIYI, year, month, day, shichen)


def make_agent(**overrides) -> Agent:
    defaults = dict(
        agent_id="A",
        location_id="city",
        location_type="城市",
        age=20,
        realm=DEFAULT_REALM_ORDER[0],
        money=10,
        satiety=50,
        cultivation=0.0,
        heart_demon=0.0,
        lifespan_left=80.0,
        flags=set(),
        inventory=Inventory(),
        time_anchor=AgentTimeAnchor(last_synced_game_time=make_time()),
        event_history=AgentEventHistory(),
        state=IdleState(),
        causes=[],
    )
    defaults.update(overrides)
    return Agent(**defaults)


def make_world(locations: dict[str, Location] | None = None) -> WorldView:
    state = WorldState(locations=locations or {})
    return WorldView(_state=state)


def make_tavern_world() -> WorldView:
    return make_world(
        {
            "city": Location("city", "某城", LocationKind.CITY, "城市"),
            "jiuguan": Location("jiuguan", "醉仙楼", LocationKind.MARKET, "酒楼"),
        }
    )


def make_balance() -> BalanceTable:
    return BalanceTable()


def make_rng(seed: int = 42) -> random.Random:
    return random.Random(seed)


class FakeScenarioRepository:
    def __init__(self, graphs: dict | None = None):
        self._graphs = graphs or {}

    def get(self, scenario_id: str):
        return self._graphs.get(scenario_id)


def make_play_turn(
    events, scenarios=None, bus=None, log=None, clock=None, parser=None, rng=None, balance=None,
    embedding=None, narrative_writer=None,
):
    """按 bootstrap.py 同样的接线方式，只是用测试用的内存仓库/固定 rng，方便
    §9 测试策略里"内存假仓库 + 固定 rng"的写法。"""
    from model.services.arbiter import EventArbiter
    from model.services.chat_parser import ChatParser
    from model.services.clock_service import GameClock
    from model.services.event_bus import InProcessEventBus
    from model.services.handlers.game_event_handler import GameEventHandler
    from model.services.handlers.result_pool_executor import ResultPoolExecutor
    from model.services.pipeline import default_pipeline
    from model.services.play_turn import PlayTurnService

    bus = bus or InProcessEventBus()
    clock = clock or GameClock(start=make_time(), bus=bus)
    balance = balance or make_balance()
    rng = rng or make_rng()
    scenarios = scenarios or FakeScenarioRepository()
    executor = ResultPoolExecutor(balance=balance, rng=rng, scenarios=scenarios)
    pipeline = default_pipeline(GameEventHandler(executor), log=log)
    if parser is None:
        alias_map = {alias: e.event_id for e in events.load_event_defs() if e.is_command for alias in e.aliases}
        # 命令未必已发布（is_draft=True 时也想在测试里解析），退化成扫全部已知事件
        if not alias_map and hasattr(events, "_events"):
            alias_map = {alias: e.event_id for e in events._events.values() if e.is_command for alias in e.aliases}
        parser = ChatParser(alias_map)
    return PlayTurnService(
        bus, EventArbiter(), pipeline, parser, events, scenarios, rng, log, clock,
        embedding=embedding, narrative_writer=narrative_writer,
    )
