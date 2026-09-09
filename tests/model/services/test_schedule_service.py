"""tests/model/services/test_schedule_service.py — 日程巡检（README 1.5.2）。

之前完全没有测试覆盖（audit 发现的缺口）：ScheduleService 存在于仓库里，但没人
验证过空闲判定、标签配额、执行器回调这几条契约。
"""
import random
import unittest

from model.domain.events import GameEventDef
from model.domain.states import ActingState, IdleState
from model.domain.time import Epoch, GameTime
from model.services.schedule_service import Schedule, ScheduleEntry, ScheduleService
from tests.helpers import make_agent


def _defn(event_id: str, tags: tuple[str, ...], weight: float = 1.0) -> GameEventDef:
    return GameEventDef(
        event_id=event_id, applicable_locations=("*",), applicable_time=None, predicate=None,
        weight=weight, duration_shichen=0, cooldown_shichen=0, max_trigger_per_agent=None,
        exclusive_tags=(), priority=5, tags=tags, aliases=(), result_pool=(), variants=(),
    )


class _FakeEventRepo:
    def __init__(self, defs: list[GameEventDef]) -> None:
        self._defs = defs

    def load_event_defs(self, location_type=None):
        return list(self._defs)


class ScheduleServiceTests(unittest.TestCase):
    def test_non_idle_agent_is_never_triggered(self):
        agent = make_agent(state=ActingState())
        events = _FakeEventRepo([_defn("chore", ("生活",))])
        calls = []
        service = ScheduleService(events, rng=random.Random(1), executor=lambda a, d, s: calls.append(d.event_id))

        service.maybe_trigger(agent, GameTime.new(Epoch.TAIYI, 100, 1, 1, 6))

        self.assertEqual(calls, [])

    def test_idle_agent_with_no_candidates_does_not_call_executor(self):
        agent = make_agent(state=IdleState())
        events = _FakeEventRepo([])
        calls = []
        service = ScheduleService(events, rng=random.Random(1), executor=lambda a, d, s: calls.append(d.event_id))

        service.maybe_trigger(agent, GameTime.new(Epoch.TAIYI, 100, 1, 1, 6))

        self.assertEqual(calls, [])

    def test_idle_agent_with_candidates_triggers_executor_with_schedule_source(self):
        from model.domain.events import TriggerSource

        agent = make_agent(state=IdleState())
        events = _FakeEventRepo([_defn("chore", ("生活",))])
        calls = []
        service = ScheduleService(events, rng=random.Random(1), executor=lambda a, d, s: calls.append((d.event_id, s)))

        service.maybe_trigger(agent, GameTime.new(Epoch.TAIYI, 100, 1, 1, 6))

        self.assertEqual(calls, [("chore", TriggerSource.SCHEDULE)])

    def test_boosted_tag_skews_selection_without_being_mandatory(self):
        """README 1.5.2："不保证该时辰必触发该事件"——boost 只改权重，不改"有没有
        候选就一定选中它"这件事；这里验证的是"高权重候选在大量抽样里明显占多数"，
        不是"每次都选中"（那是配额，不是随机）。"""
        agent = make_agent(state=IdleState())
        events = _FakeEventRepo([_defn("chore", ("生活",), weight=1.0), _defn("meditate_flavor", ("修炼",), weight=1.0)])
        schedule = Schedule(entries=[ScheduleEntry(shichen=(6,), boosted_tag="修炼", weight_multiplier=20.0)])
        picks = []
        service = ScheduleService(
            events, rng=random.Random(1), schedules={"npc": schedule},
            executor=lambda a, d, s: picks.append(d.event_id),
        )
        agent.agent_id = "npc"

        for _ in range(30):
            service.maybe_trigger(agent, GameTime.new(Epoch.TAIYI, 100, 1, 1, 6))

        self.assertGreater(picks.count("meditate_flavor"), picks.count("chore"))

    def test_set_schedule_is_the_only_public_mutation_point(self):
        service = ScheduleService(_FakeEventRepo([]), rng=random.Random(1))
        schedule = Schedule(entries=[ScheduleEntry(shichen=(6,), boosted_tag="修炼")])

        service.set_schedule("npc", schedule)

        self.assertIs(service._schedules["npc"], schedule)


if __name__ == "__main__":
    unittest.main()
