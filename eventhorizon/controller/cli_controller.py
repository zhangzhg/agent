"""controller/cli_controller.py — MVP 入口（对应 README §7）；ws_controller 放到
V1。

只负责一个 stdin/stdout 循环，把玩家输入转给已经装配好的 ChatController；不直调
pipeline / matching / arbiter（那些接线在 bootstrap.py 组合根里完成）。开局叙述
用 content/onboarding.py 的静态文案（GAME_DESIGN §1.1），每轮附带一行角色/位置
状态摘要，遵循 §2.4 的数值展示克制原则（境界+进度条、寿元模糊态、饱食图标）。
"""
from __future__ import annotations

import sys

from bootstrap import build_app
from content.seed import seed_all
from content.session import ensure_seed_agent
from controller.chat_controller import ChatController


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


def run_repl(agent_id: str = "player") -> None:
    app = build_app()
    seed_all(app)
    ensure_seed_agent(app, agent_id)
    controller = ChatController(app.agent_repo, app.world_repo, app.play_turn, app.events)

    print("《太一仙途》CLI（Ctrl+C 退出）")
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
    run_repl(sys.argv[1] if len(sys.argv) > 1 else "player")
