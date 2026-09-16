"""controller/web_controller.py — FastAPI 入口（README §3.2 / §5）。

薄：只做 HTTP 请求/响应的编解码，业务全部委派给 ChatController（跟
chat_controller.py 是同一个类，CLI 和 Web 两个入口共用）。不直调
pipeline / matching / arbiter——那些接线仍然全部在 bootstrap.py 完成。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from controller.admin_controller import register_admin_routes
from controller.play_session import open_play_session
from model.repositories.llm.llm_event_flavor_author import LlmEventFlavorAuthor
from model.repositories.llm.llm_item_author import LlmItemAuthor
from model.repositories.llm.llm_location_author import LlmLocationAuthor
from model.repositories.llm.llm_result_text_parser import LlmResultTextParser
from model.services.character_service import (
    EVENT_EXPIRED_NARRATIVE,
    CharacterAuthError,
    CharacterExistsError,
    InvalidAgentIdError,
)
from view.schemas.web_schemas import (
    CalendarPanelDTO,
    ChatApiRequest,
    ChatApiResponse,
    CharacterCreateRequest,
    CharacterCreateResponse,
    CharacterEnterRequest,
    CharacterPanelDTO,
    LocationPanelDTO,
    SidebarDTO,
)
from view.templating import STATIC_DIR, templates

if TYPE_CHECKING:
    from bootstrap import AppContext


def create_app(db_path: str | None = None) -> FastAPI:
    session = open_play_session(db_path)
    app_ctx = session.app
    controller = session.controller
    llm_client = session.llm_client
    embedding_client = session.embedding

    fastapi_app = FastAPI(title="太一仙途")
    fastapi_app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")  # theme.css 等两页共用资源

    @fastapi_app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "chat.html")

    @fastapi_app.post("/api/character", response_model=CharacterCreateResponse)
    def create_character(request: CharacterCreateRequest) -> CharacterCreateResponse:
        try:
            created = app_ctx.character_service.create(request.agent_id)
        except InvalidAgentIdError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except CharacterExistsError:
            raise HTTPException(status_code=409, detail="这个人物账号已经有人用了。") from None
        return CharacterCreateResponse(agent_id=created.agent_id, verify_code=created.verify_code)

    @fastapi_app.post("/api/session", response_model=ChatApiResponse)
    def session(request: CharacterEnterRequest) -> ChatApiResponse:
        """进入游戏：校验人物 id + 验证码；事件快照超过三天则清任务挂起、保留修为行囊。"""
        agent, event_expired = _enter_character(app_ctx, request.agent_id, request.verify_code)
        parts: list[str] = []
        if event_expired:
            parts.append(EVENT_EXPIRED_NARRATIVE)
        if agent.turn_count == 0:
            from content.onboarding import OPENING_NARRATIVE

            parts.append(OPENING_NARRATIVE)
        return ChatApiResponse(
            narrative="\n\n".join(parts),
            agent_state=agent.state.name,
            sidebar=_build_sidebar(app_ctx, agent.agent_id),
            event_expired=event_expired,
        )

    @fastapi_app.post("/api/chat", response_model=ChatApiResponse)
    def chat(request: ChatApiRequest) -> ChatApiResponse:
        _authenticate(app_ctx, request.agent_id, request.verify_code)
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
    )  # /admin + /api/admin/*（README §1.3.3）

    return fastapi_app


def _authenticate(app_ctx: "AppContext", agent_id: str, verify_code: str) -> None:
    try:
        app_ctx.character_service.authenticate(agent_id, verify_code)
    except InvalidAgentIdError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except CharacterAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def _enter_character(app_ctx: "AppContext", agent_id: str, verify_code: str):
    try:
        entered = app_ctx.character_service.enter(agent_id, verify_code)
    except InvalidAgentIdError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except CharacterAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=401, detail="人物 id 或验证码不对。") from exc
    return entered.agent, entered.event_expired


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
