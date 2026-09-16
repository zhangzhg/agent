"""controller/cli_controller.py — MVP 入口（对应 README §7）；ws_controller 放到
V1。

只负责一个 stdin/stdout 循环，把玩家输入转给已经装配好的 ChatController；不直调
pipeline / matching / arbiter（那些接线在 bootstrap.py 组合根里完成）。开局叙述
用 content/onboarding.py 的静态文案（README §3.2），每轮附带一行角色/位置
状态摘要，遵循 §2.4 的数值展示克制原则（境界+进度条、寿元模糊态、饱食图标）。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from bootstrap import DEFAULT_DB_PATH, build_app
from content.seed import seed_all
from controller.chat_controller import ChatController
from model.services.character_service import (
    EVENT_EXPIRED_NARRATIVE,
    CharacterAuthError,
    CharacterExistsError,
    InvalidAgentIdError,
)


def _print_status_line(app, agent_id: str) -> None:
    from view.character_panel_view import build_character_panel
    from view.location_panel_view import build_location_panel

    agent = app.agent_repo.load(agent_id)
    world = app.world_repo.assemble_view()
    char_panel = build_character_panel(agent, app.balance)
    loc_panel = build_location_panel(agent.location_id, world)
    print(
        f"  [{loc_panel.name} · {loc_panel.location_type} 灵气{loc_panel.qi_density_icons}]"
        f" {char_panel.cultivation_progress_text} 饱食{char_panel.satiety_icons}"
        f" 金钱{char_panel.money}"
    )


def _prompt(message: str) -> str:
    return input(message).strip()


def _create_character(app) -> tuple[str, str]:
    while True:
        agent_id = _prompt("人物 id（2～16 个字）：")
        try:
            created = app.character_service.create(agent_id)
        except InvalidAgentIdError as exc:
            print(exc)
            continue
        except CharacterExistsError:
            print("这个人物 id 已经有人用了。")
            continue
        print(f"验证码（只显示一次，请抄下）：{created.verify_code}")
        return created.agent_id, created.verify_code


def _enter_character(app, agent_id: str = "", verify_code: str = ""):
    while True:
        if not agent_id:
            agent_id = _prompt("人物 id：")
        if not verify_code:
            verify_code = _prompt("验证码：")
        try:
            return app.character_service.enter(agent_id, verify_code)
        except (InvalidAgentIdError, CharacterAuthError) as exc:
            print(exc)
            agent_id = ""
            verify_code = ""


def run_repl() -> None:
    db_path = os.environ.get("EVENTHORIZON_DB_PATH") or str(DEFAULT_DB_PATH)
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    app = build_app(db_path=db_path)
    if not app.world.locations:
        seed_all(app)
    controller = ChatController(
        app.agent_repo, app.world_repo, app.play_turn, app.events,
        rng=app.rng, characters=app.character_service,
    )

    print("《太一仙途》CLI（Ctrl+C 退出）")
    print("1) 建立人物")
    print("2) 进入游戏")
    preset_id = sys.argv[1] if len(sys.argv) > 1 else ""
    choice = "2" if preset_id else ""
    while choice not in ("1", "2"):
        choice = _prompt("请选择 1 或 2：")

    try:
        if choice == "1":
            agent_id, verify_code = _create_character(app)
            entered = _enter_character(app, agent_id, verify_code)
        else:
            entered = _enter_character(app, preset_id)
    except (EOFError, KeyboardInterrupt):
        print("\n再会。")
        return

    agent_id = entered.agent.agent_id
    if entered.event_expired:
        print(EVENT_EXPIRED_NARRATIVE)
    if entered.agent.turn_count == 0:
        from content.onboarding import OPENING_NARRATIVE

        print(OPENING_NARRATIVE)
    while True:
        try:
            raw = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再会。")
            return
        if not raw:
            continue
        response = controller.on_player_message(raw, agent_id)
        print(response.narrative)
        for line in response.state_diff_lines:
            print(f"  · {line}")
        if response.agent_state != "dead":
            _print_status_line(app, agent_id)


if __name__ == "__main__":
    run_repl()
