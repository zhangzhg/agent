import unittest

from model.domain.cause import CauseLink
from model.domain.diff import AppliedDiff, LocationAttrChange, WorldDiff, apply_agent_diff, apply_world_diff, merge
from model.domain.map import Location, LocationKind, WorldState
from tests.helpers import make_agent


class ApplyAgentDiffTests(unittest.TestCase):
    def test_attr_deltas_accumulate(self):
        agent = make_agent(money=10, satiety=50)
        apply_agent_diff(agent, AppliedDiff(attr_deltas=(("money", -3.0), ("satiety", 5.0))))
        self.assertEqual(agent.money, 7.0)
        self.assertEqual(agent.satiety, 55.0)

    def test_items_and_flags(self):
        agent = make_agent()
        apply_agent_diff(agent, AppliedDiff(items_add=(("玉佩", 1),), flags_set=("已拜师",)))
        self.assertTrue(agent.inventory.has("玉佩"))
        self.assertIn("已拜师", agent.flags)
        apply_agent_diff(agent, AppliedDiff(items_remove=(("玉佩", 1),), flags_clear=("已拜师",)))
        self.assertFalse(agent.inventory.has("玉佩"))
        self.assertNotIn("已拜师", agent.flags)

    def test_pending_encounter_set_and_clear(self):
        agent = make_agent()
        apply_agent_diff(agent, AppliedDiff(pending_encounter_set="fish"))
        self.assertEqual(agent.pending_encounter_id, "fish")
        apply_agent_diff(agent, AppliedDiff(pending_encounter_set=""))
        self.assertIsNone(agent.pending_encounter_id)

    def test_unset_diff_does_not_touch_pending_scenario(self):
        agent = make_agent()
        agent.pending_scenario = None
        apply_agent_diff(agent, AppliedDiff())  # 默认 diff：未涉及任何挂起字段
        self.assertIsNone(agent.pending_scenario)

    def test_state_set_reconstructs_state_object(self):
        agent = make_agent()
        apply_agent_diff(agent, AppliedDiff(state_set="closed_door"))
        self.assertEqual(agent.state.name, "closed_door")

    def test_causes_add_appends(self):
        agent = make_agent()
        link = CauseLink(actor="A", action="kill", target="B", tag="仇恨")
        apply_agent_diff(agent, AppliedDiff(causes_add=(link,)))
        self.assertIn(link, agent.causes)


class MergeTests(unittest.TestCase):
    def test_attr_deltas_sum_across_merge(self):
        a = AppliedDiff(attr_deltas=(("money", -1.0),))
        b = AppliedDiff(attr_deltas=(("money", -2.0), ("satiety", 3.0)))
        merged = merge(a, b)
        self.assertEqual(dict(merged.attr_deltas), {"money": -3.0, "satiety": 3.0})

    def test_second_write_wins_for_single_value_fields(self):
        a = AppliedDiff(realm_set="练气")
        b = AppliedDiff(realm_set="筑基")
        self.assertEqual(merge(a, b).realm_set, "筑基")

    def test_unset_sentinel_does_not_clobber_pending_scenario(self):
        a = AppliedDiff(pending_scenario_set=None)  # 显式清空
        b = AppliedDiff()  # 未涉及（哨兵值）
        self.assertIsNone(merge(a, b).pending_scenario_set)


class WorldDiffTests(unittest.TestCase):
    def test_invert_swaps_old_and_new(self):
        diff = WorldDiff(location_changes=(LocationAttrChange("loc1", "danger_level", 0.1, 0.9),))
        inverted = diff.invert()
        self.assertEqual(inverted.location_changes[0].old, 0.9)
        self.assertEqual(inverted.location_changes[0].new, 0.1)

    def test_apply_then_invert_round_trips(self):
        world = WorldState(locations={"loc1": Location("loc1", "废墟前身", LocationKind.WILDERNESS, "荒野", danger_level=0.1)})
        diff = WorldDiff(location_changes=(LocationAttrChange("loc1", "danger_level", 0.1, 0.9),))
        apply_world_diff(world, diff)
        self.assertEqual(world.locations["loc1"].danger_level, 0.9)
        apply_world_diff(world, diff.invert())
        self.assertEqual(world.locations["loc1"].danger_level, 0.1)


if __name__ == "__main__":
    unittest.main()
