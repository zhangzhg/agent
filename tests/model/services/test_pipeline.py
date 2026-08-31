import unittest

from model.domain.diff import AppliedDiff
from model.domain.events import EventVariant, GameEventDef, GameEventOccurrence, TriggerSource
from model.domain.predicates import Predicate, PredicateGroup, PredicateType
from model.repositories.event_log import InMemoryEventLogStore
from model.services.pipeline import ApplyDiffStep, LogStep, PipelineContext, ValidationStep, default_pipeline
from tests.helpers import make_agent, make_time, make_world


def _def(predicate=None):
    return GameEventDef(
        event_id="e1",
        applicable_locations=("*",),
        applicable_time=None,
        predicate=predicate,
        weight=1.0,
        duration_shichen=1,
        cooldown_shichen=0,
        max_trigger_per_agent=None,
        exclusive_tags=(),
        priority=5,
        tags=(),
        aliases=(),
        result_pool=(),
        variants=(EventVariant("v0"),),
    )


class _AddsDiffHandler:
    def handle(self, ctx):
        from model.domain.diff import merge

        ctx.diff = merge(ctx.diff, AppliedDiff(attr_deltas=(("money", -1.0),)))


class _StoppingHandler:
    """模拟"突破失败 → 走火入魔"：链内 stop，已产出的扣除仍要落地。"""

    def handle(self, ctx):
        from model.domain.diff import merge

        ctx.diff = merge(ctx.diff, AppliedDiff(attr_deltas=(("heart_demon", 5.0),)))
        ctx.stopped = True


def _occ():
    return GameEventOccurrence("e1", TriggerSource.PLAYER, "A", make_time(), 0)


class PipelineTests(unittest.TestCase):
    def test_predicate_failure_rejects_no_apply_no_log(self):
        agent = make_agent(money=10)
        world = make_world()
        log = InMemoryEventLogStore()
        failing_predicate = PredicateGroup("AND", (Predicate(PredicateType.MONEY_GTE, (999,)),))
        pipeline = default_pipeline(_AddsDiffHandler(), log=log)
        ctx = pipeline.run(PipelineContext(_occ(), _def(failing_predicate), agent, world))
        self.assertTrue(ctx.rejected)
        self.assertEqual(agent.money, 10)  # 状态未改
        self.assertEqual(log._entries, [])  # 无日志

    def test_success_applies_and_logs(self):
        agent = make_agent(money=10)
        world = make_world()
        log = InMemoryEventLogStore()
        pipeline = default_pipeline(_AddsDiffHandler(), log=log)
        ctx = pipeline.run(PipelineContext(_occ(), _def(), agent, world))
        self.assertFalse(ctx.rejected)
        self.assertEqual(agent.money, 9.0)
        self.assertEqual(len(log._entries), 1)
        self.assertIsNotNone(log._entries[0].applied_diff)

    def test_stopped_still_applies_and_logs_partial_diff(self):
        """rejected 与 stopped 必须分开：stopped 是"算到一半不再往下算，但已发生的照落"。"""
        agent = make_agent(heart_demon=0.0)
        world = make_world()
        log = InMemoryEventLogStore()
        pipeline = default_pipeline(_StoppingHandler(), log=log)
        ctx = pipeline.run(PipelineContext(_occ(), _def(), agent, world))
        self.assertFalse(ctx.rejected)
        self.assertTrue(ctx.stopped)
        self.assertEqual(agent.heart_demon, 5.0)  # 已产出的扣除仍然生效
        self.assertEqual(len(log._entries), 1)

    def test_validation_step_alone_marks_rejected(self):
        agent = make_agent(money=0)
        world = make_world()
        step = ValidationStep()
        ctx = PipelineContext(_occ(), _def(PredicateGroup("AND", (Predicate(PredicateType.MONEY_GTE, (5,)),))), agent, world)
        step.handle(ctx)
        self.assertTrue(ctx.rejected)


if __name__ == "__main__":
    unittest.main()
