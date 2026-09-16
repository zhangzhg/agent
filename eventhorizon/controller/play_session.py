"""controller/play_session.py — CLI 与 Web 共用的对局装配。

两边必须走这一份：同一 sqlite、同一 LLM、同一本地向量、同一 ChatController。
Admin 录入作者仍只在 web_controller 里接线，不进对局路径。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from bootstrap import DEFAULT_DB_PATH, build_app
from content.seed import seed_all
from controller.chat_controller import ChatController
from model.repositories.llm.llm_config import load_llm_config
from model.repositories.llm.openai_compatible_client import OpenAiCompatibleClient
from model.services.local_embedding import FallbackEmbeddingClient
from model.services.world_query_assistant import WorldQueryAssistant

if TYPE_CHECKING:
    from bootstrap import AppContext


@dataclass
class PlaySession:
    app: "AppContext"
    controller: ChatController
    llm_client: OpenAiCompatibleClient | None
    embedding: FallbackEmbeddingClient


def resolve_db_path(db_path: str | None = None) -> str:
    if db_path is None:
        db_path = os.environ.get("EVENTHORIZON_DB_PATH") or str(DEFAULT_DB_PATH)
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return db_path


def open_play_session(db_path: str | None = None) -> PlaySession:
    db_path = resolve_db_path(db_path)
    llm_config = load_llm_config()
    llm_client = OpenAiCompatibleClient(llm_config) if llm_config.configured else None
    embedding = FallbackEmbeddingClient(None)  # 对局向量走本地模型，不打远端 /embeddings
    app = build_app(db_path=db_path, embedding=embedding, narrative_writer=llm_client)
    if not app.world.locations:
        seed_all(app)
    world_query = WorldQueryAssistant(llm_client) if llm_client is not None else None
    controller = ChatController(
        app.agent_repo, app.world_repo, app.play_turn, app.events,
        rng=app.rng, world_query=world_query, characters=app.character_service,
    )
    return PlaySession(app=app, controller=controller, llm_client=llm_client, embedding=embedding)
