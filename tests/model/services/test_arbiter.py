import unittest

from model.domain.events import TriggerSource
from model.services.arbiter import ArbitrationDecision, EventArbiter


class ArbiterTests(unittest.TestCase):
    def setUp(self):
        self.arbiter = EventArbiter()

    def test_force_always_executes(self):
        for state in ("idle", "acting", "closed_door", "encounter_pending", "scenario_pending", "dead"):
            self.assertEqual(
                self.arbiter.decide(state, TriggerSource.FORCE, 5, None), ArbitrationDecision.EXECUTE
            )

    def test_dead_discards_non_force(self):
        self.assertEqual(
            self.arbiter.decide("dead", TriggerSource.PLAYER, 5, None), ArbitrationDecision.DISCARD
        )

    def test_closed_door_discards_non_force(self):
        self.assertEqual(
            self.arbiter.decide("closed_door", TriggerSource.SCHEDULE, 5, None), ArbitrationDecision.DISCARD
        )
        self.assertEqual(
            self.arbiter.decide("closed_door", TriggerSource.PLAYER, 5, None), ArbitrationDecision.DISCARD
        )

    def test_pending_states_only_accept_player(self):
        for state in ("encounter_pending", "scenario_pending"):
            self.assertEqual(
                self.arbiter.decide(state, TriggerSource.PLAYER, 5, None), ArbitrationDecision.EXECUTE
            )
            self.assertEqual(
                self.arbiter.decide(state, TriggerSource.SCHEDULE, 5, None), ArbitrationDecision.DISCARD
            )
            self.assertEqual(
                self.arbiter.decide(state, TriggerSource.ENCOUNTER, 5, None), ArbitrationDecision.DISCARD
            )

    def test_acting_encounter_enqueues_not_executes(self):
        # 回归项：曾把 ENQUEUE 当 EXECUTE，等于奇遇抢占了主行为
        decision = self.arbiter.decide("acting", TriggerSource.ENCOUNTER, 5, 3)
        self.assertEqual(decision, ArbitrationDecision.ENQUEUE)

    def test_acting_player_preempts(self):
        self.assertEqual(
            self.arbiter.decide("acting", TriggerSource.PLAYER, 5, 3), ArbitrationDecision.EXECUTE
        )

    def test_acting_schedule_compares_priority(self):
        # 数字小 = 优先级高；同来源下按事件配置等级比
        self.assertEqual(
            self.arbiter.decide("acting", TriggerSource.SCHEDULE, 1, 5), ArbitrationDecision.EXECUTE
        )
        self.assertEqual(
            self.arbiter.decide("acting", TriggerSource.SCHEDULE, 9, 5), ArbitrationDecision.DISCARD
        )

    def test_idle_executes(self):
        self.assertEqual(
            self.arbiter.decide("idle", TriggerSource.PLAYER, 5, None), ArbitrationDecision.EXECUTE
        )


if __name__ == "__main__":
    unittest.main()
