"""content/npc.py — MVP 示例 NPC 与日程（README §3.6，衔接 ScheduleService）。

npc_generation.generate_npc 只是纯函数（产出一个 Agent），得有人真的调用它、把
产物存进仓库、并给至少一个 NPC 配上日程，ScheduleService 才有巡检对象——否则
"接线"只是让 TimePassHandler 每次都拿到一个空的 agents_provider() 列表，等于没接。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from content.map import CANGJIAN, CANGWU_TAVERN
from model.domain.time import Epoch, GameTime
from model.services.npc_generation import NpcGenerationParams, generate_npc
from model.services.schedule_service import Schedule, ScheduleEntry

if TYPE_CHECKING:
    from bootstrap import AppContext

# 王掌柜：苍梧城·醉仙楼，午时（酉时前后)偏"生活"标签——酒楼掌柜白天多半在照看生意。
TAVERN_KEEPER_ID = "王掌柜"
# 赵师姐：藏剑山门，卯时偏"修炼"标签——同门弟子清早多半在打坐用功。
SECT_DISCIPLE_ID = "赵师姐"

_MIDDAY_SHICHEN = (6, 7)  # 午时/未时
_DAWN_SHICHEN = (2, 3)  # 卯时/辰时


def seed_npcs(app: "AppContext") -> None:
    """种两个 MVP 示例 NPC + 各自的日程，供 ScheduleService 巡检验证。"""
    birth_time = GameTime.new(Epoch.TAIYI, 70, 1, 1, 6)  # 比主角年长三十年，示意性设定

    tavern_keeper = generate_npc(
        NpcGenerationParams(
            agent_id=TAVERN_KEEPER_ID,
            location_id=CANGWU_TAVERN,
            location_type="酒楼",
            age=45,
            birth_time=birth_time,
            origin="商贾",
        ),
        rng=app.rng,
    )
    app.agent_repo.save(tavern_keeper)
    app.schedule_service.set_schedule(
        TAVERN_KEEPER_ID, Schedule(entries=[ScheduleEntry(shichen=_MIDDAY_SHICHEN, boosted_tag="生活")])
    )

    sect_disciple = generate_npc(
        NpcGenerationParams(
            agent_id=SECT_DISCIPLE_ID,
            location_id=CANGJIAN,
            location_type="山门",
            age=19,
            birth_time=birth_time,
            origin="宗门弟子",
        ),
        rng=app.rng,
    )
    app.agent_repo.save(sect_disciple)
    app.schedule_service.set_schedule(
        SECT_DISCIPLE_ID, Schedule(entries=[ScheduleEntry(shichen=_DAWN_SHICHEN, boosted_tag="修炼")])
    )
