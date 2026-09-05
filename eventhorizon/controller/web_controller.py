"""controller/web_controller.py — FastAPI 入口（GAME_DESIGN §2 的 Web 版，
ARCHITECTURE §10："V1+ 需要真正的聊天前端时，建议 FastAPI"）。

薄：只做 HTTP 请求/响应的编解码，业务全部委派给 ChatController（跟
chat_controller.py 是同一个类，CLI 和 Web 两个入口共用）。不直调
pipeline / matching / arbiter——那些接线仍然全部在 bootstrap.py 完成。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from bootstrap import build_app
from content.seed import seed_all
from content.session import ensure_seed_agent
from controller.admin_controller import register_admin_routes
from controller.chat_controller import ChatController
from model.repositories.llm.llm_config import load_llm_config
from model.repositories.llm.llm_event_flavor_author import LlmEventFlavorAuthor
from model.repositories.llm.llm_item_author import LlmItemAuthor
from model.repositories.llm.llm_location_author import LlmLocationAuthor
from model.repositories.llm.llm_result_text_parser import LlmResultTextParser
from model.repositories.llm.openai_compatible_client import OpenAiCompatibleClient
from view.schemas.web_schemas import (
    CalendarPanelDTO,
    ChatApiRequest,
    ChatApiResponse,
    CharacterPanelDTO,
    LocationPanelDTO,
    SidebarDTO,
)
from view.templating import STATIC_DIR, templates

if TYPE_CHECKING:
    from bootstrap import AppContext

# 网页版默认落一个真的 sqlite 文件（bootstrap.build_app() 自己的默认值是
# ":memory:"，那是给测试用的，测试要的就是每次都从空白状态开始，互不污染）——
# 录入编辑器存的地图/物品/事件是要长期攒的内容，进程一重启就清空说不过去。
# 路径按这个文件的位置算，不依赖当前工作目录（start.sh 会先 cd 到 eventhorizon/，
# 但直接用相对路径不如算绝对路径稳）；EVENTHORIZON_DB_PATH 可以整个覆盖掉。
DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "eventhorizon.db"


def create_app(db_path: str | None = None) -> FastAPI:
    if db_path is None:
        db_path = os.environ.get("EVENTHORIZON_DB_PATH") or str(DEFAULT_DB_PATH)
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    llm_config = load_llm_config()
    llm_client = OpenAiCompatibleClient(llm_config) if llm_config.configured else None
    # embed() 和 complete() 用的是同一个 OpenAiCompatibleClient 实例（同一个连接，
    # 两种能力）；只有 embedding_model 也配了才把它当 EmbeddingPort 接进对局路径
    # （PlayTurnService 的 predicate_text 向量判定），没配就是 None，等同于向量
    # 模块关闭（fail-open，见 model/services/matching.py）。
    embedding_client = llm_client if llm_config.embedding_configured else None
    # narrative_writer 复用同一个 complete()——LlmEventWriter（README 对局第二段
    # 表格）：事件命中但 variants 留空时现场补一句文案，见 PlayTurnService._ensure_variants。

    app_ctx = build_app(db_path=db_path, embedding=embedding_client, narrative_writer=llm_client)
    if not app_ctx.world.locations:
        # 空库（真·第一次跑，或者用的是 :memory:）才灌种子内容——已经有数据的库
        # 再灌一遍：locations 是按 id upsert 还好，但 routes 是直接 extend，会
        # 越滚越多重复；events/items 也会把用户在编辑器里改过的同 id 内容悄悄
        # 冲回种子原文，两种都不是"重启后应该发生的事"。
        seed_all(app_ctx)
    controller = ChatController(app_ctx.agent_repo, app_ctx.world_repo, app_ctx.play_turn, app_ctx.events)

    fastapi_app = FastAPI(title="太一仙途")
    fastapi_app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")  # theme.css 等两页共用资源

    @fastapi_app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse("chat.html", {"request": request})

    @fastapi_app.get("/api/session", response_model=ChatApiResponse)
    def session(agent_id: str = Query(default="player")) -> ChatApiResponse:
        """页面首次加载 / 刷新时调用：新会话给一句开局叙述（GAME_DESIGN §1.1），
        老会话只回当前状态栏，不重复播报开场白。"""
        agent = ensure_seed_agent(app_ctx, agent_id)
        narrative = ""
        if agent.turn_count == 0:
            from content.onboarding import OPENING_NARRATIVE

            narrative = OPENING_NARRATIVE
        return ChatApiResponse(
            narrative=narrative,
            agent_state=agent.state.name,
            sidebar=_build_sidebar(app_ctx, agent_id),
        )

    @fastapi_app.post("/api/chat", response_model=ChatApiResponse)
    def chat(request: ChatApiRequest) -> ChatApiResponse:
        ensure_seed_agent(app_ctx, request.agent_id)
        response = controller.on_player_message(request.text, request.agent_id)
        return ChatApiResponse(
            narrative=response.narrative,
            state_diff_lines=response.state_diff_lines,
            agent_state=response.agent_state,
            parse_error=response.parse_error,
            reject_reason=response.reject_reason,
            sidebar=_build_sidebar(app_ctx, request.agent_id),
        )

    llm_location_author = LlmLocationAuthor(llm_client) if llm_client else None
    llm_item_author = LlmItemAuthor(llm_client) if llm_client else None
    llm_event_flavor_author = LlmEventFlavorAuthor(llm_client) if llm_client else None
    llm_result_text_parser = LlmResultTextParser(llm_client) if llm_client else None
    register_admin_routes(
        fastapi_app, app_ctx, llm_location_author, llm_item_author, llm_event_flavor_author,
        embedding_client, llm_result_text_parser,
    )  # /admin + /api/admin/*（ARCHITECTURE §1.3.3）

    return fastapi_app


def _build_sidebar(app_ctx: "AppContext", agent_id: str) -> SidebarDTO:
    from view.calendar_view import render_calendar_plaque
    from view.character_panel_view import build_character_panel
    from view.location_panel_view import build_location_panel

    agent = app_ctx.agent_repo.load(agent_id)
    world = app_ctx.world_repo.assemble_view()
    calendar = render_calendar_plaque(app_ctx.clock.now())
    character = build_character_panel(agent, app_ctx.balance)
    location = build_location_panel(agent.location_id, world)
    return SidebarDTO(
        calendar=CalendarPanelDTO(text=calendar.text, is_tidal_day=calendar.is_tidal_day),
        location=LocationPanelDTO(
            name=location.name,
            location_type=location.location_type,
            qi_density_icons=location.qi_density_icons,
            weather=location.weather,
        ),
        character=CharacterPanelDTO(
            realm=character.realm,
            cultivation_progress_text=character.cultivation_progress_text,
            lifespan_label=character.lifespan_label,
            satiety_icons=character.satiety_icons,
            money=character.money,
            inventory_count=character.inventory_count,
        ),
    )


app = create_app()  # uvicorn controller.web_controller:app 这种标准写法需要模块级变量


def run_web(host: str = "127.0.0.1", port: int = 8765) -> None:
    import uvicorn

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    import sys

    host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8765
    run_web(host, port)
