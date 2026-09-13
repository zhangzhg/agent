"""model/services/game_context_tools.py — 公共的游戏上下文只读 Function Call
工具集（README §1.13 关联章节：世界信息问答）。

跟 live_content_author.py/play_turn.py 里"地点创作时查真实地点列表"是同一路数
（真正的 function calling，见 model/services/llm_tool_loop.py）——这里把"读玩家
状态/读当前地点/读全图/读可达地点"抽成公共、可被多处复用的工具，不再各自为政
地内联一份。第一个消费者是 world_query_assistant.py（回答"我在哪里""附近有哪些
城市"这类元问题），以后别的实时创作 prompt 想先摸清玩家现状，也直接拿这几个
工具用，不用重新发明。

全部只读、不改任何状态——工具本身不受 README §1.12"对局隔离"约束，跟
EmbeddingPort 是同一类"对局路径本来就该能用"的能力。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from model.domain.agent import Agent
    from model.domain.map import WorldView


def get_player_status(agent: "Agent", world: "WorldView") -> dict:
    """玩家自身状态——回答"我在哪里""我是什么境界""我还有多少钱""现在什么时候
    了"这类问题的事实来源。"""
    from model.domain.time import GameCalendar

    return {
        "location_id": agent.location_id,
        "location_name": world.name_of(agent.location_id),
        "location_type": agent.location_type,
        "realm": agent.realm,
        "age": agent.age,
        "money": agent.money,
        "satiety": agent.satiety,
        "cultivation": agent.cultivation,
        "heart_demon": agent.heart_demon,
        "flags": sorted(agent.flags),
        "game_time": GameCalendar.plaque_text(agent.time_anchor.current_game_time),
    }


def get_current_location(agent: "Agent", world: "WorldView") -> dict:
    """当前所在地点的详细信息——不止类型标签，还有天气/灵气浓度/地点状态这些
    叙事细节，回答"这里是什么地方""这儿安全吗"之类的追问。"""
    condition = world.condition_of(agent.location_id)
    return {
        "location_id": agent.location_id,
        "name": world.name_of(agent.location_id),
        "location_type": agent.location_type,
        "condition": condition.value if condition is not None else None,
        "qi_density": world.qi_density_of(agent.location_id),
        "weather": world.weather(),
    }


def list_all_locations(world: "WorldView") -> list[dict]:
    """全图当前对玩家可见的地点（未被神识扫描发现的隐藏点位不列入——不能凭空
    剧透还没被发现的秘境，跟 WorldView.find_location_by_name 的可见性规则一致，
    也是 play_turn.py::_author_live_destination_outcome 里同一份可见性过滤的
    公共版本）。"""
    state = world.mutable_state()
    return [
        {"location_id": loc.location_id, "name": loc.name, "location_type": loc.location_type, "kind": loc.kind.value}
        for loc in state.locations.values()
        if not loc.hidden or loc.discovered
    ]


def list_reachable_locations(agent: "Agent", world: "WorldView") -> list[dict]:
    """从玩家当前地点出发、有直接路径（Route）可达的相邻地点——回答"离我最近的
    城市有哪些"。按 move_cost_shichen 从小到大排序，越靠前越"近"。"""
    state = world.mutable_state()
    out = []
    for route in state.neighbors(agent.location_id):
        loc = state.get(route.to_id)
        if loc is None or (loc.hidden and not loc.discovered):
            continue
        out.append({
            "location_id": loc.location_id,
            "name": loc.name,
            "location_type": loc.location_type,
            "move_cost_shichen": route.move_cost_shichen,
        })
    out.sort(key=lambda item: item["move_cost_shichen"])
    return out


def _tool_spec(name: str, description: str) -> dict:
    return {
        "type": "function",
        "function": {"name": name, "description": description, "parameters": {"type": "object", "properties": {}}},
    }


def build_tool_specs() -> list[dict]:
    """OpenAI 风格的工具定义数组，四个工具都不需要参数——所需上下文（agent/
    world）由调用方在 build_tool_impls 里通过闭包绑定，不劳模型传参。"""
    return [
        _tool_spec("get_player_status", "查询玩家自身当前状态：所在地点、境界、年龄、金钱、饱食度、修为、心魔值、已获得的身份标记、当前游戏时间"),
        _tool_spec("get_current_location", "查询玩家当前所在地点的详细信息：地点名称、类型、状态（完好/废墟/秘境开启）、灵气浓度、天气"),
        _tool_spec("list_all_locations", "查询游戏世界里当前对玩家可见的所有地点列表（尚未被神识扫描发现的隐藏地点不包含在内）"),
        _tool_spec("list_reachable_locations", "查询从玩家当前所在地点出发、有直接路径可达的相邻地点列表，按移动耗时从近到远排序"),
    ]


def build_tool_impls(agent: "Agent", world: "WorldView") -> dict[str, Callable[[], object]]:
    return {
        "get_player_status": lambda: get_player_status(agent, world),
        "get_current_location": lambda: get_current_location(agent, world),
        "list_all_locations": lambda: list_all_locations(world),
        "list_reachable_locations": lambda: list_reachable_locations(agent, world),
    }
