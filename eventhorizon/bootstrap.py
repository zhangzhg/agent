"""bootstrap.py — 组合根：把 model.services / model.repositories 的各个部件接线成
一个可跑的 App（对应 README 3 技术方案的"默认路径"接线）。

之所以不放进 controller/：README 3.7 与 §9 架构守卫测试要求 controller/** 不
import pipeline / matching / arbiter——那三个薄入口只该拿到已经装配好的
ChatController / EditorController，不该自己拼线。真正的 DI 组装集中在这里。
"""
from __future__ import annotations

import random
import sqlite3
from dataclasses import dataclass

from model.domain.balance import BalanceTable
from model.domain.map import WorldState
from model.domain.system_events import DeathEvent, MapUpdateEvent, TimePassEvent
from model.domain.time import Epoch, GameTime
from model.repositories.agent_repository import SqliteAgentRepository
from model.repositories.event_log import SqliteEventLogStore
from model.repositories.item_repository import SqliteItemRepository
from model.repositories.snapshot_store import SqliteSnapshotStore
from model.repositories.sqlite_event_repository import SqliteEventRepository
from model.repositories.world_repository import SqliteWorldRepository
from model.services.arbiter import EventArbiter
from model.services.chat_parser import ChatParser
from model.services.clock_service import GameClock, RetreatService
from model.services.death_service import DeathService
from model.services.event_bus import InProcessEventBus
from model.services.handlers.death_handler import DeathHandler
from model.services.handlers.game_event_handler import GameEventHandler
from model.services.handlers.map_update_handler import MapUpdateHandler
from model.services.handlers.result_pool_executor import ResultPoolExecutor
from model.services.handlers.time_pass_handler import TimePassHandler
from model.services.pipeline import default_pipeline
from model.services.play_turn import PlayTurnService
from model.services.live_narrative_writer import LlmClient
from model.services.ports import EmbeddingPort


@dataclass
class ScenarioRepositoryImpl:
    """MVP：内存字典，流程图是录入产物，随事件库一起分发。"""

    graphs: dict = None

    def __post_init__(self) -> None:
        self.graphs = self.graphs or {}

    def get(self, scenario_id: str):
        return self.graphs.get(scenario_id)


@dataclass
class AppContext:
    conn: sqlite3.Connection
    bus: InProcessEventBus
    clock: GameClock
    world: WorldState
    events: SqliteEventRepository
    items: SqliteItemRepository
    scenarios: ScenarioRepositoryImpl
    agent_repo: SqliteAgentRepository
    world_repo: SqliteWorldRepository
    play_turn: PlayTurnService
    retreat: RetreatService
    death_service: DeathService
    balance: BalanceTable


def build_app(
    db_path: str = ":memory:",
    seed_time: GameTime | None = None,
    rng_seed: int | None = None,
    embedding: "EmbeddingPort | None" = None,
    narrative_writer: "LlmClient | None" = None,
) -> AppContext:
    # check_same_thread=False：FastAPI 把同步路由丢进线程池执行，不同请求可能落
    # 在不同线程上（哪怕从不真正并发），sqlite3 默认的单线程校验会直接报错。单机
    # 单玩家场景不会有真正的并发写，这里放开检查是安全的简化（README 1.1 产品边界）。
    conn = sqlite3.connect(db_path, check_same_thread=False)
    bus = InProcessEventBus()
    balance = BalanceTable()
    rng = random.Random(rng_seed)

    events = SqliteEventRepository(conn)
    items = SqliteItemRepository(conn)
    scenarios = ScenarioRepositoryImpl()
    logs = SqliteEventLogStore(conn)
    snapshots = SqliteSnapshotStore(conn)
    agent_repo = SqliteAgentRepository(snapshots, logs)
    world_repo = SqliteWorldRepository(snapshots)

    now = seed_time or GameTime.new(Epoch.TAIYI, 100, 1, 1, 6)
    clock = GameClock(start=now, bus=bus)

    executor = ResultPoolExecutor(balance=balance, rng=rng, scenarios=scenarios)
    handler = GameEventHandler(executor)
    pipeline = default_pipeline(handler, log=logs)
    parser = _build_chat_parser(events)
    arbiter = EventArbiter()
    retreat = RetreatService(clock, balance, rng, log=logs)

    play_turn = PlayTurnService(
        bus, arbiter, pipeline, parser, events, scenarios, rng, logs, clock,
        retreat=retreat, balance=balance, embedding=embedding, narrative_writer=narrative_writer,
    )

    world_view = world_repo.assemble_view()
    world_state = world_view.mutable_state()
    bus.subscribe(MapUpdateEvent, MapUpdateHandler(world_state).handle)
    bus.subscribe(TimePassEvent, TimePassHandler(world_state).handle)

    death_service = DeathService()
    bus.subscribe(DeathEvent, DeathHandler(death_service, agent_repo).handle)

    play_turn.bind_context(world_repo.assemble_view, agent_repo.load)

    return AppContext(
        conn=conn,
        bus=bus,
        clock=clock,
        world=world_state,
        events=events,
        items=items,
        scenarios=scenarios,
        agent_repo=agent_repo,
        world_repo=world_repo,
        play_turn=play_turn,
        retreat=retreat,
        death_service=death_service,
        balance=balance,
    )


def _build_chat_parser(events: SqliteEventRepository) -> ChatParser:
    alias_to_event_id: dict[str, str] = {}
    for defn in events.load_event_defs():
        if not defn.is_command:
            continue
        for alias in defn.aliases:
            alias_to_event_id[alias] = defn.event_id
    return ChatParser(alias_to_event_id)


def refresh_chat_parser(app: AppContext) -> None:
    """build_app() 建 parser 时事件库通常还是空的（内容还没灌进去）；content
    包 seed 完事件后调这个，把别名表重建一遍。不重建 PlayTurnService 本身，只换
    parser 这一个字段——其它接线（pipeline/arbiter/clock）都不受影响。"""
    app.play_turn.parser = _build_chat_parser(app.events)
