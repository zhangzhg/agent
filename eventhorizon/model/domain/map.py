"""model/domain/map.py — 虚拟地图模型（对应 README 1.2.2）。

图结构：Location 节点 + Route 边。世界层手编、城市内节点按模板生成、建筑内部
按需加载嵌套子图——这些生成策略在 services/repositories 落地，domain 只定义结构。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class LocationKind(str, Enum):
    CITY = "城市"
    WILDERNESS = "荒野"
    CAVE = "洞府"
    MARKET = "集市"
    SECT_GATE = "山门"
    RUIN = "遗迹"
    SECRET_REALM = "秘境"


class LocationCondition(str, Enum):
    """地点薄状态（对应 README 3.3 世界侧状态）：完好 / 废墟 / 秘境开启。
    MapUpdateEvent 只触发状态对象的进入/离开逻辑，不在节点上堆 if。"""

    INTACT = "完好"
    RUINED = "废墟"
    SECRET_OPENED = "秘境开启"


@dataclass(slots=True)
class Location:
    """地图节点：坐标、类型、属性（灵气浓度、危险等级）。"""

    location_id: str
    name: str
    kind: LocationKind
    location_type: str  # 供谓词 location_type() 与事件 applicable_locations 匹配的通配类型标签
    x: float = 0.0
    y: float = 0.0
    qi_density: float = 1.0
    danger_level: float = 0.0
    condition: LocationCondition = LocationCondition.INTACT
    parent_location_id: str | None = None  # 建筑内部子图的父节点；也用于挂"藏在哪个地点底下"的隐藏点位

    # —— 探索反馈（GAME_DESIGN §5.3 神识扫描）——
    hidden: bool = False  # 未扫描前不出现在常规地点列表 / 移动目的地里
    concealment: float = 0.0  # 隐蔽度：扫描命中概率，示意 0.15~0.40
    discovered: bool = False  # 扫描命中后翻真；持久化在 WorldState 里，不因重连丢失


@dataclass(frozen=True, slots=True)
class Route:
    """节点间的连通性及移动消耗。"""

    from_id: str
    to_id: str
    move_cost_shichen: int = 1
    bidirectional: bool = True


@dataclass(slots=True)
class WorldState:
    """世界地图的可写状态：节点表 + 边表 + 全局天气。ApplyDiffStep 是唯一改它的地方。"""

    locations: dict[str, Location] = field(default_factory=dict)
    routes: list[Route] = field(default_factory=list)
    weather: str = "晴"

    def get(self, location_id: str) -> Location | None:
        return self.locations.get(location_id)

    def neighbors(self, location_id: str) -> list[Route]:
        out = []
        for r in self.routes:
            if r.from_id == location_id:
                out.append(r)
            elif r.bidirectional and r.to_id == location_id:
                out.append(Route(location_id, r.from_id, r.move_cost_shichen, True))
        return out


# 别名：WorldMap 是 WorldState 的手编/录入侧叫法，两者是同一结构。
WorldMap = WorldState


@dataclass(slots=True)
class WorldView:
    """world 的只读视图（TODO #5：目前仍通过 mutable_state() 暴露可写引用给
    ApplyDiffStep，这是全系统唯一允许绕过"只读"的调用点；其余代码一律走这里的
    只读方法）。由 services 组装，domain 本身不碰 IO。"""

    _state: WorldState
    now_provider: "object | None" = None  # 由 clock_service 注入的可调用，返回当前 GameTime

    def location_type_of(self, location_id: str) -> str:
        loc = self._state.get(location_id)
        return loc.location_type if loc else ""

    def qi_density_of(self, location_id: str) -> float:
        loc = self._state.get(location_id)
        return loc.qi_density if loc else 1.0

    def name_of(self, location_id: str) -> str:
        loc = self._state.get(location_id)
        return loc.name if loc else location_id

    def condition_of(self, location_id: str) -> "LocationCondition | None":
        loc = self._state.get(location_id)
        return loc.condition if loc else None

    def weather(self) -> str:
        return self._state.weather

    def find_location_by_name(self, hint: str) -> Location | None:
        """"去{地点}"式移动命令的模糊匹配（GAME_DESIGN §3.1："地点名走模糊匹配，
        不要求精确"）：先精确匹配 id/名称，再退化成子串匹配；隐藏未发现的地点不参与
        匹配（不能靠打字凭空"去"一个还没被神识扫描发现的秘境）。"""
        hint = hint.strip()
        if not hint:
            return None
        visible = [loc for loc in self._state.locations.values() if not loc.hidden or loc.discovered]
        for loc in visible:
            if loc.location_id == hint or loc.name == hint or loc.location_type == hint:
                return loc
        for loc in visible:
            if hint in loc.name or loc.name in hint or hint in loc.location_type or loc.location_type in hint:
                return loc
        return None

    def hidden_candidates_at(self, parent_location_id: str) -> list[Location]:
        """某地点下尚未被发现的隐藏点位，供神识扫描只读查询（GAME_DESIGN §5.3）。"""
        return [
            loc
            for loc in self._state.locations.values()
            if loc.hidden and not loc.discovered and loc.parent_location_id == parent_location_id
        ]

    def mutable_state(self) -> WorldState:
        """可写引用的唯一出口。绝大多数调用者应该是责任链里的 ApplyDiffStep；少数
        独立于责任链之外、但仍然只通过 apply_world_diff 写状态的批量/探索类服务
        （如 exploration_service 的神识扫描发现点位）也经这里拿引用——约束不是
        "只有 ApplyDiffStep 能调用"，而是"不管谁调用，写入都必须走 apply_world_diff/
        apply_agent_diff，不允许绕过 diff 直接 setattr"。"""
        return self._state
