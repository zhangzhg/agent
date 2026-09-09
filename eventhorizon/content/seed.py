"""content/seed.py — 把 content/ 下的地图、事件、物品灌进已经装配好的 App
（bootstrap.build_app() 的产物）。MVP 演示 / 集成测试用的一次性灌装脚本。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from content import map as content_map
from content.events import cangjian, cangwu, commands, guixu, heifeng, luoyan, universal
from content.items import ALL as ALL_ITEMS
from content.npc import seed_npcs

if TYPE_CHECKING:
    from bootstrap import AppContext

ALL_EVENTS = commands.ALL + cangwu.ALL + luoyan.ALL + cangjian.ALL + heifeng.ALL + guixu.ALL + universal.ALL


def seed_world(app: "AppContext") -> None:
    mvp_world = content_map.build_mvp_world()
    app.world.locations.update(mvp_world.locations)
    app.world.routes.extend(mvp_world.routes)


def seed_events(app: "AppContext") -> None:
    for defn in ALL_EVENTS:
        app.events.save_event_def(defn)


def seed_items(app: "AppContext") -> None:
    for item in ALL_ITEMS:
        app.items.save_item_def(item)


def seed_all(app: "AppContext") -> None:
    """一次性把地图/事件/物品/NPC 都灌进去，并刷新 ChatParser 的别名表
    （build_app() 建 app 时事件库还是空的，ChatParser 那时候建不出正确的别名表）。
    NPC 必须排在事件/地图之后种：seed_npcs() 里生成的 Agent 引用了 content.map 的
    地点 id，日程标签命中与否也取决于事件库是否已经灌好。"""
    from bootstrap import refresh_chat_parser

    seed_world(app)
    seed_events(app)
    seed_items(app)
    seed_npcs(app)
    refresh_chat_parser(app)
    app.world_repo.save(app.clock.now())
