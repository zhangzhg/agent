"""model/services/ports.py — 端口定义（依赖倒置，对应 README 5.1）。

services 只依赖这些 Protocol，测试时可以直接用内存字典实现假对象，不需要真数据库；
repositories 只负责实现。谁使用端口谁定义接口，这是依赖倒置的标准放法。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from model.domain.agent import Agent
    from model.domain.balance import BalanceTable
    from model.domain.events import GameEventDef, GameEventOccurrence
    from model.domain.items import ItemDef
    from model.domain.map import WorldView
    from model.domain.scenario import ScenarioGraph
    from model.domain.time import GameTime


class AgentRepository(Protocol):
    """controller/chat_controller.py 的 agent_repo.load/save 用它。README 未单列此
    端口——单存档/单主角下，Agent 持久化落在 5.2 的快照 + 增量日志基础设施上，这里
    只是给 controller 一个薄的读/写立面，不新增独立的 CRUD 存储格式。"""

    def load(self, agent_id: str) -> "Agent": ...
    def save(self, agent: "Agent") -> None: ...


class WorldRepository(Protocol):
    """controller/chat_controller.py 的 world_repo.assemble_view() 用它，组装只读
    WorldView 交给 play_turn，不把可写 WorldState 泄漏到 controller。save() 把
    WorldState 的当前内容落盘——地图状态（地点 condition、神识扫描发现的隐藏点位等）
    否则只活在进程内存里，重启即丢。"""

    def assemble_view(self) -> "WorldView": ...
    def save(self, at: "GameTime") -> None: ...


class ItemRepository(Protocol):
    """背包面板"点击查看物品描述"用（GAME_DESIGN §2.6）。README/ARCHITECTURE 没有
    单列物品仓库端口——物品之前只作为 item_id 字符串出现在 Result / ValidationCatalog
    里；这里补上最小的读接口，不引入独立的物品录入流程。"""

    def get_by_id(self, item_id: str) -> "ItemDef | None": ...


class EventRepository(Protocol):
    def get_by_id(self, event_id: str) -> "GameEventDef | None": ...
    def load_event_defs(self, location_type: str | None = None) -> list["GameEventDef"]: ...
    def save_event_def(self, event: "GameEventDef") -> None: ...


class ScenarioRepository(Protocol):
    """PlayTurnService 用它把 pending_scenario.scenario_id 换回图；图本身是录入产物。"""

    def get(self, scenario_id: str) -> "ScenarioGraph | None": ...


class BalanceRepository(Protocol):
    def load(self, version: str | None = None) -> "BalanceTable": ...


class SnapshotStore(Protocol):
    def save_snapshot(self, world_state: dict, at: "GameTime") -> None: ...
    def load_latest_snapshot(self) -> tuple[dict, "GameTime"] | None: ...


class EventLogStore(Protocol):
    def append(self, occurrence: "GameEventOccurrence") -> None: ...
    def replay_since(self, since: "GameTime") -> list["GameEventOccurrence"]: ...


class EmbeddingPort(Protocol):
    def embed(self, text: str) -> list[float]: ...


class LlmAuthorPort(Protocol):
    """仅被 model/repositories/llm 与 controller/editor_controller.py 使用；
    model/services 对局路径（play_turn / matching / chat_parser）不持有此端口。"""

    def generate_draft(self, description: str, constraints: dict) -> list["GameEventDef"]: ...
