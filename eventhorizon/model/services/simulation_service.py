"""model/services/simulation_service.py — 录入页"模拟触发"沙盒（对应 README
1.3.3 测试沙盒）。

不用启动完整游戏客户端就能验收一条事件：跑一遍粗筛 + 谓词，显示是否进入合格
池、相对其它候选的权重占比、随机抽样 N 次的命中分布。

之所以单独成一个 services 模块，而不是让 editor_controller.py 直接
`import model.services.matching`：README §9 架构守卫测试要求 controller/**
不得直调 pipeline / matching / arbiter。模拟沙盒确实要复用 1.4.2 那套
粗筛+重排（不能自己再写一份，否则就是编辑器与运行时两套标准），所以这层薄封装
就是"controller 只能拿到已经装配好的用例"这条规则要求的那一层。
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

from model.domain.predicates import EvalContext
from model.domain.time import Epoch, GameTime
from model.services.matching import MatchContext, coarse_filter, reweight_and_pick

if TYPE_CHECKING:
    from model.domain.agent import AgentEventHistory
    from model.services.ports import EventRepository


@dataclass
class SimulationOutcome:
    passed_coarse_filter: bool
    relative_weight_share: float
    hit_distribution: dict[str, int]


class SnapshotEvalContext(EvalContext):
    """把编辑器传入的测试快照 dict 适配成 EvalContext，与 matching.py /
    scenario_executor.py 的运行时谓词求值走同一份 PredicateGroup。"""

    def __init__(self, snapshot: dict) -> None:
        self._snapshot = snapshot

    def attr(self, name: str) -> float:
        return float(self._snapshot.get(name, 0))

    def realm_rank(self) -> int:
        from model.domain.balance import DEFAULT_REALM_ORDER

        realm = self._snapshot.get("境界", DEFAULT_REALM_ORDER[0])
        return DEFAULT_REALM_ORDER.index(realm) if realm in DEFAULT_REALM_ORDER else -1

    def money(self) -> int:
        return self._snapshot.get("金钱", 0)

    def age(self) -> int:
        return self._snapshot.get("年龄", 0)

    def has_item(self, item_id: str) -> bool:
        return item_id in self._snapshot.get("物品", ())

    def flag(self, name: str) -> bool:
        return name in self._snapshot.get("标志", ())

    def location_type(self) -> str:
        return self._snapshot.get("地点类型", "")

    def has_cause(self, tag: str, target: str) -> bool:
        return (tag, target) in self._snapshot.get("因果", ())


def simulate_trigger(
    events: "EventRepository",
    event_id: str,
    context_snapshot: dict,
    history: "AgentEventHistory",
    sample_n: int,
    rng: random.Random,
) -> SimulationOutcome:
    snap = context_snapshot
    pool = events.load_event_defs(snap.get("地点类型"))
    now = GameTime.new(Epoch.TAIYI, snap.get("年份", 1), snap.get("月", 1), snap.get("日", 1), snap.get("时辰", 0))
    mctx = MatchContext(
        location=snap.get("地点", ""),
        location_type=snap.get("地点类型", ""),
        time_shichen=now.shichen,
        now=now,
        age=snap.get("年龄", 0),
        realm=snap.get("境界", ""),
        money=snap.get("金钱", 0),
        causes=[],
    )
    eval_ctx = SnapshotEvalContext(snap)
    candidates = coarse_filter(pool, mctx, eval_ctx, history)
    target = events.get_by_id(event_id)
    passed = target is not None and target in candidates
    total_weight = sum(c.weight for c in candidates) or 1.0
    share = (target.weight / total_weight) if (passed and target is not None) else 0.0

    distribution: dict[str, int] = {}
    for _ in range(sample_n):
        picked = reweight_and_pick(candidates, history, rng)
        if picked is not None:
            distribution[picked.event_id] = distribution.get(picked.event_id, 0) + 1

    return SimulationOutcome(passed_coarse_filter=passed, relative_weight_share=share, hit_distribution=distribution)
