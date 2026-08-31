"""model/services/scenario_executor.py — 流程图执行引擎（对应 README 1.3.1 / 4.10）。

无状态。进度存 Agent.pending_scenario，跨回合靠存档带走；原先把 _context_stack
挂在实例上的做法，存读档会丢失流程图进度。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from model.domain.agent import PendingScenario
from model.domain.scenario import ScenarioGraph, ScenarioNode

if TYPE_CHECKING:
    from model.domain.predicates import EvalContext


class ScenarioExecutor:
    """无状态：进度存 Agent.pending_scenario。"""

    def start(self, graph: ScenarioGraph, host_event_id: str) -> tuple[ScenarioNode, PendingScenario]:
        node = graph.entry_node()
        return node, PendingScenario(graph.scenario_id, node.node_id, host_event_id)

    def advance(
        self,
        graph: ScenarioGraph,
        current_node_id: str,
        eval_ctx: "EvalContext",
        chosen_edge_id: str | None = None,
    ) -> ScenarioNode | None:
        """chosen_edge_id 来自 ParsedReply（玩家下一句选的边）；为 None 时按谓词自动走
        唯一满足的边。"""
        for edge in graph.edges_from(current_node_id):
            if chosen_edge_id is not None and edge.edge_id != chosen_edge_id:
                continue
            if edge.condition.evaluate(eval_ctx):
                return graph.node(edge.to_id)
        return None  # 无边满足则本条事件内流程结束，PlayTurn 清空 pending_scenario
