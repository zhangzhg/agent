import unittest

from model.domain.events import GameEventOccurrence, TriggerSource
from model.domain.states import (
    ActingState,
    ClosedDoorState,
    DeadState,
    EncounterPendingState,
    IdleState,
    ScenarioPendingState,
    state_by_name,
)
from tests.helpers import make_agent, make_time


def _occ(source: TriggerSource) -> GameEventOccurrence:
    return GameEventOccurrence("e1", source, "A", make_time(), 0)


class StateMachineTests(unittest.TestCase):
    def test_idle_accepts_player_schedule_force_encounter_and_chain(self):
        # CHAIN 必须被 idle 接受：execute_occurrence / _resolve_reply_option 都是先
        # settle() 回 idle，再执行连锁事件——idle 若拒绝 CHAIN，任何链式事件都会在
        # try_transition 这一步被吞掉，diff 根本不会产生（曾经是真实 bug）。
        agent = make_agent()
        for source in (
            TriggerSource.PLAYER, TriggerSource.SCHEDULE, TriggerSource.FORCE,
            TriggerSource.ENCOUNTER, TriggerSource.CHAIN,
        ):
            self.assertIsInstance(IdleState().try_transition(agent, _occ(source)), ActingState)

    def test_closed_door_only_force_breaks_it(self):
        agent = make_agent()
        self.assertIsNone(ClosedDoorState().try_transition(agent, _occ(TriggerSource.PLAYER)))
        self.assertIsNone(ClosedDoorState().try_transition(agent, _occ(TriggerSource.SCHEDULE)))
        self.assertIsInstance(ClosedDoorState().try_transition(agent, _occ(TriggerSource.FORCE)), ActingState)

    def test_dead_rejects_everything_and_settle_is_absorbing(self):
        agent = make_agent()
        dead = DeadState()
        for source in TriggerSource:
            self.assertIsNone(dead.try_transition(agent, _occ(source)))
        self.assertIs(dead.settle(agent), dead)

    def test_encounter_pending_rejects_schedule_and_encounter(self):
        agent = make_agent()
        self.assertIsNone(EncounterPendingState().try_transition(agent, _occ(TriggerSource.SCHEDULE)))
        self.assertIsNone(EncounterPendingState().try_transition(agent, _occ(TriggerSource.ENCOUNTER)))
        self.assertIsInstance(EncounterPendingState().try_transition(agent, _occ(TriggerSource.PLAYER)), ActingState)
        self.assertIsInstance(EncounterPendingState().try_transition(agent, _occ(TriggerSource.CHAIN)), ActingState)

    def test_settle_prefers_scenario_then_encounter_then_idle(self):
        agent = make_agent(pending_encounter_id="fish_event")
        self.assertEqual(ActingState().settle(agent).name, "encounter_pending")
        agent.pending_encounter_id = None
        self.assertEqual(ActingState().settle(agent).name, "idle")

    def test_state_by_name_round_trip(self):
        for cls in (IdleState, ActingState, ClosedDoorState, EncounterPendingState, ScenarioPendingState, DeadState):
            self.assertIsInstance(state_by_name(cls.name), cls)

    def test_state_by_name_unknown_raises(self):
        with self.assertRaises(ValueError):
            state_by_name("not_a_state")


if __name__ == "__main__":
    unittest.main()
