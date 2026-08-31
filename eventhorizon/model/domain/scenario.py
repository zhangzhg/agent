"""model/domain/scenario.py — 可视化流程图数据结构（对应 README 1.3.1）。

支持通过前端界面定制单条事件内部的分支，底座负责解析和执行。不用于编排全局主线；
流程图节点/边只能引用同一个 scenario_id 内的节点——构造时校验，杜绝跨事件跳转。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from model.domain.predicates import PredicateGroup


class ScenarioNodeKind(str, Enum):
    DIALOGUE = "dialogue"
    NARRATION = "narration"
    COMBAT = "combat"
    ITEM_GAIN = "item_gain"


@dataclass(frozen=True, slots=True)
class ScenarioNode:
    """节点：类型（对话、旁白、战斗、获得物品）、内容文本、参数（如战斗 ID）。"""

    node_id: str
    kind: ScenarioNodeKind
    text: str = ""
    params: dict = field(default_factory=dict)
    results: tuple = field(default_factory=tuple)  # 命中该节点时执行的 Result（同一条 pipeline）


@dataclass(frozen=True, slots=True)
class ScenarioEdge:
    """从节点 A 到节点 B 的跳转条件；条件只允许谓词白名单组合，不做字符串 eval。"""

    edge_id: str
    from_id: str
    to_id: str
    condition: PredicateGroup
    aliases: tuple[str, ...] = ()  # 玩家下一句可直接命中的局部选项短语


class ScenarioGraphError(ValueError):
    """流程图结构非法：孤立节点、跨 scenario 引用、环等（供 event_validation 复用）。"""


@dataclass(slots=True)
class ScenarioGraph:
    scenario_id: str
    nodes: dict[str, ScenarioNode]
    edges: list[ScenarioEdge]
    entry_node_id: str

    def __post_init__(self) -> None:
        if self.entry_node_id not in self.nodes:
            raise ScenarioGraphError(f"entry node {self.entry_node_id!r} not in graph {self.scenario_id!r}")
        for edge in self.edges:
            if edge.from_id not in self.nodes or edge.to_id not in self.nodes:
                raise ScenarioGraphError(
                    f"edge {edge.edge_id!r} references a node outside scenario {self.scenario_id!r} "
                    "(禁止引用主线步骤/章节 id 或别的 scenario)"
                )

    def entry_node(self) -> ScenarioNode:
        return self.nodes[self.entry_node_id]

    def node(self, node_id: str) -> ScenarioNode | None:
        return self.nodes.get(node_id)

    def edges_from(self, node_id: str) -> list[ScenarioEdge]:
        return [e for e in self.edges if e.from_id == node_id]

    def has_orphan_nodes(self) -> bool:
        """孤立节点检测：入口之外，没有任何入边的节点视为孤立（供 §4.12 校验复用）。"""
        reachable_targets = {e.to_id for e in self.edges}
        reachable_targets.add(self.entry_node_id)
        return any(node_id not in reachable_targets for node_id in self.nodes)

    def has_cycle(self) -> bool:
        """简单环检测（DFS），供录入校验复用。"""
        visiting: set[str] = set()
        visited: set[str] = set()

        def dfs(node_id: str) -> bool:
            if node_id in visiting:
                return True
            if node_id in visited:
                return False
            visiting.add(node_id)
            for edge in self.edges_from(node_id):
                if dfs(edge.to_id):
                    return True
            visiting.discard(node_id)
            visited.add(node_id)
            return False

        return dfs(self.entry_node_id)
