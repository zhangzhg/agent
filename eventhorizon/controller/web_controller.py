"""controller/web_controller.py — FastAPI 入口（GAME_DESIGN §2 的 Web 版，
ARCHITECTURE §10："V1+ 需要真正的聊天前端时，建议 FastAPI"）。

薄：只做 HTTP 请求/响应的编解码，业务全部委派给 ChatController（跟
chat_controller.py 是同一个类，CLI 和 Web 两个入口共用）。不直调
pipeline / matching / arbiter——那些接线仍然全部在 bootstrap.py 完成。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse

from bootstrap import build_app
from content.seed import seed_all
from content.session import ensure_seed_agent
from controller.admin_controller import register_admin_routes
from controller.chat_controller import ChatController
from view.schemas.web_schemas import (
    CalendarPanelDTO,
    ChatApiRequest,
    ChatApiResponse,
    CharacterPanelDTO,
    LocationPanelDTO,
    SidebarDTO,
)
from view.web.chat_page import render_page

if TYPE_CHECKING:
    from bootstrap import AppContext


def create_app() -> FastAPI:
    app_ctx = build_app()
    seed_all(app_ctx)
    controller = ChatController(app_ctx.agent_repo, app_ctx.world_repo, app_ctx.play_turn, app_ctx.events)

    fastapi_app = FastAPI(title="太一仙途")

    @fastapi_app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return render_page()

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

    register_admin_routes(fastapi_app, app_ctx)  # /admin + /api/admin/*（ARCHITECTURE §1.3.3）

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
