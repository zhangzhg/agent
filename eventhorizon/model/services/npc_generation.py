"""model/services/npc_generation.py — NPC 生成规则（GAME_DESIGN §6.1）。

灵根：五行随机，可复合。资质：正态分布，均值对应"中人之姿"，影响修炼速度倍率
0.5x~2.0x。运势：均匀分布，影响奇遇标签权重加成。出身：按出生地城市模板抽
（商贾/农家/散修/宗门弟子），决定初始 flags 与可用别名。
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from model.domain.agent import Agent, AgentEventHistory
from model.domain.balance import DEFAULT_REALM_ORDER
from model.domain.items import Inventory
from model.domain.states import IdleState
from model.domain.time import AgentTimeAnchor, GameTime

_FIVE_ELEMENTS = ("金", "木", "水", "火", "土")
_ORIGINS = ("商贾", "农家", "散修", "宗门弟子")
_ORIGIN_FLAGS = {
    "商贾": ("擅长议价",),
    "农家": (),
    "散修": ("居无定所",),
    "宗门弟子": ("有门派归属",),
}
_DUAL_ROOT_CHANCE = 0.3  # 复合灵根概率（策划配置示意值，文档未给出精确数字）
_APTITUDE_MEAN = 1.0
_APTITUDE_STD = 0.35
_APTITUDE_MIN, _APTITUDE_MAX = 0.5, 2.0
_LUCK_MIN, _LUCK_MAX = -0.2, 0.2


def generate_spirit_root(rng: random.Random) -> str:
    """五行随机，可复合，如"水木双灵根"。"""
    if rng.random() < _DUAL_ROOT_CHANCE:
        a, b = rng.sample(_FIVE_ELEMENTS, 2)
        return f"{a}{b}双灵根"
    return f"{rng.choice(_FIVE_ELEMENTS)}灵根"


def generate_aptitude(rng: random.Random) -> float:
    """正态分布，均值对应"中人之姿"，影响修炼速度倍率 0.5x~2.0x（§6.1）。"""
    value = rng.gauss(_APTITUDE_MEAN, _APTITUDE_STD)
    return max(_APTITUDE_MIN, min(_APTITUDE_MAX, value))


def generate_luck(rng: random.Random) -> float:
    """均匀分布，影响奇遇标签权重加成（隐藏谓词 luck_gte 读它，见 §7.5）。"""
    return rng.uniform(_LUCK_MIN, _LUCK_MAX)


def generate_origin(rng: random.Random) -> str:
    """按出生地城市模板抽（商贾/农家/散修/宗门弟子）。"""
    return rng.choice(_ORIGINS)


@dataclass
class NpcGenerationParams:
    agent_id: str
    location_id: str
    location_type: str
    age: int
    birth_time: GameTime
    origin: str | None = None  # None 则随机


def generate_npc(params: NpcGenerationParams, rng: random.Random | None = None) -> Agent:
    """产出一个完整的 NPC Agent，可直接经 AgentRepository.save() 落库，供
    npc_query_service / biography_service 查询、matching.py 参与合格池粗筛。"""
    rng = rng or random.Random()
    origin = params.origin or generate_origin(rng)
    return Agent(
        agent_id=params.agent_id,
        location_id=params.location_id,
        location_type=params.location_type,
        age=params.age,
        realm=DEFAULT_REALM_ORDER[0],
        money=rng.randint(5, 50),
        satiety=100,
        cultivation=0.0,
        heart_demon=0.0,
        lifespan_left=80.0,
        flags=set(_ORIGIN_FLAGS.get(origin, ())),
        inventory=Inventory(),
        time_anchor=AgentTimeAnchor(last_synced_game_time=params.birth_time),
        event_history=AgentEventHistory(),
        state=IdleState(),
        causes=[],
        spirit_root=generate_spirit_root(rng),
        aptitude=generate_aptitude(rng),
        luck=generate_luck(rng),
        insight=generate_luck(rng),  # 悟性沿用同一套均匀分布，文档未给出独立公式
        origin=origin,
    )
