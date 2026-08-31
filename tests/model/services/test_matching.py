import random
import unittest

from model.domain.agent import AgentEventHistory
from model.domain.events import EventVariant, GameEventDef
from model.domain.predicates import Predicate, PredicateGroup, PredicateType
from model.services.matching import MatchContext, coarse_filter, pick_variant, reweight_and_pick
from tests.helpers import make_time


def _def(event_id, **overrides):
    defaults = dict(
        event_id=event_id,
        applicable_locations=("*",),
        applicable_time=None,
        predicate=None,
        weight=1.0,
        duration_shichen=1,
        cooldown_shichen=0,
        max_trigger_per_agent=None,
        exclusive_tags=(),
        priority=5,
        tags=(),
        aliases=(),
        result_pool=(),
        variants=(EventVariant("v0"), EventVariant("v1")),
        is_draft=False,
        is_command=False,
    )
    defaults.update(overrides)
    return GameEventDef(**defaults)


class _Ctx:
    def money(self):
        return 0

    def attr(self, name):
        return 0

    def realm_rank(self):
        return 0

    def age(self):
        return 0

    def has_item(self, item_id):
        return False

    def flag(self, name):
        return False

    def location_type(self):
        return "酒楼"

    def has_cause(self, tag, target):
        return False


class CoarseFilterTests(unittest.TestCase):
    def setUp(self):
        self.now = make_time()
        self.mctx = MatchContext(
            location="jiuguan", location_type="酒楼", time_shichen=self.now.shichen, now=self.now,
            age=20, realm="凡人", money=10, causes=[],
        )
        self.ctx = _Ctx()

    def test_draft_excluded(self):
        history = AgentEventHistory()
        pool = [_def("e1", is_draft=True)]
        self.assertEqual(coarse_filter(pool, self.mctx, self.ctx, history), [])

    def test_location_mismatch_excluded(self):
        history = AgentEventHistory()
        pool = [_def("e1", applicable_locations=("山门",))]
        self.assertEqual(coarse_filter(pool, self.mctx, self.ctx, history), [])

    def test_wildcard_location_included(self):
        history = AgentEventHistory()
        pool = [_def("e1", applicable_locations=("*",))]
        self.assertEqual([e.event_id for e in coarse_filter(pool, self.mctx, self.ctx, history)], ["e1"])

    def test_cooldown_is_hard_cutoff_not_weight_penalty(self):
        history = AgentEventHistory()
        history.record("e1", self.now, (), 0)
        pool = [_def("e1", cooldown_shichen=100)]
        # 冷却期内必须彻底不出现（不是降权）
        self.assertEqual(coarse_filter(pool, self.mctx, self.ctx, history), [])

    def test_max_trigger_exhausted_excluded(self):
        history = AgentEventHistory()
        history.record("e1", self.now, (), 0)
        pool = [_def("e1", max_trigger_per_agent=1)]
        self.assertEqual(coarse_filter(pool, self.mctx, self.ctx, history), [])

    def test_exclusive_tag_conflict_excluded(self):
        history = AgentEventHistory()
        history.record("e1", self.now, (), 0, exclusive_tags=("癫狂",), cooldown_shichen=1000)
        pool = [_def("e2", exclusive_tags=("癫狂",))]
        self.assertEqual(coarse_filter(pool, self.mctx, self.ctx, history), [])

    def test_predicate_failure_excluded(self):
        history = AgentEventHistory()
        pool = [_def("e1", predicate=PredicateGroup("AND", (Predicate(PredicateType.MONEY_GTE, (999,)),)))]
        self.assertEqual(coarse_filter(pool, self.mctx, self.ctx, history), [])

    def test_zero_weight_chain_only_event_excluded(self):
        """回归测试：weight<=0 的"只能被 chain 触发"事件（如金龙鱼揭晓）必须彻底
        不进候选池，否则冷却期把其它候选清空后，它会单独留下把总权重砸成 0，
        reweight_and_pick 底下的 random.choices 会直接抛异常，整回合崩掉。"""
        history = AgentEventHistory()
        pool = [_def("chain_only", weight=0.0)]
        self.assertEqual(coarse_filter(pool, self.mctx, self.ctx, history), [])


class RewardPickTests(unittest.TestCase):
    def test_reweight_and_pick_empty_returns_none(self):
        self.assertIsNone(reweight_and_pick([], AgentEventHistory(), random.Random(1)))

    def test_reweight_and_pick_all_zero_weight_returns_none_not_raises(self):
        """防御性兜底：即使有候选混进了池子（比如 extra_weight 把权重砸成 0），
        也应该退化成"抽空"而不是抛异常崩掉整回合。"""
        pool = [_def("e1", weight=0.0)]
        result = reweight_and_pick(pool, AgentEventHistory(), random.Random(1))
        self.assertIsNone(result)

    def test_zero_trigger_gets_rarity_bonus_over_many_samples(self):
        history = AgentEventHistory()
        now = make_time()
        history.record("common", now, (), 0)
        pool = [_def("common", weight=1.0), _def("rare", weight=1.0)]
        rng = random.Random(7)
        picks = [reweight_and_pick(pool, history, rng).event_id for _ in range(500)]
        # "rare" 从未触发过，长尾保护应让它的命中占比明显高于 common
        self.assertGreater(picks.count("rare"), picks.count("common"))

    def test_pick_variant_avoids_immediate_repeat(self):
        history = AgentEventHistory()
        defn = _def("e1", variants=(EventVariant("a"), EventVariant("b")))
        history.record("e1", make_time(), (), 0)  # 上次用了下标 0
        rng = random.Random(3)
        for _ in range(20):
            self.assertEqual(pick_variant(defn, history, rng), 1)

    def test_pick_variant_single_variant_is_zero(self):
        defn = _def("e1", variants=(EventVariant("only"),))
        self.assertEqual(pick_variant(defn, AgentEventHistory(), random.Random()), 0)


if __name__ == "__main__":
    unittest.main()
