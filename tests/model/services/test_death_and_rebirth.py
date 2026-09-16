import unittest

from model.domain.events import EventVariant, GameEventDef
from model.domain.results import StateChange
from model.domain.time import SHICHEN_PER_YEAR
from model.repositories.sqlite_event_repository import InMemoryEventRepository
from model.services.clock_service import GameClock, RetreatService
from model.services.death_service import DeathService, RebirthPath
from tests.helpers import make_agent, make_balance, make_play_turn, make_tavern_world, make_time, make_world


def _eat() -> GameEventDef:
    return GameEventDef(
        event_id="eat",
        applicable_locations=("*",),
        applicable_time=None,
        predicate=None,
        weight=1.0,
        duration_shichen=1,
        cooldown_shichen=0,
        max_trigger_per_agent=None,
        exclusive_tags=(),
        priority=5,
        tags=("生活",),
        aliases=("吃饭",),
        result_pool=(StateChange(field="satiety", delta=1),),
        variants=(EventVariant("你吃了口东西。"),),
        is_command=True,
        is_draft=False,
    )


class DeathServiceTests(unittest.TestCase):
    def test_handle_death_clears_all_pending_and_sets_dead(self):
        from model.domain.agent import PendingClarification, PendingLiveResult, PendingScenario

        agent = make_agent(lifespan_left=0.0)
        agent.pending_encounter_id = "x"
        agent.pending_scenario = PendingScenario("s", "n", "h")
        agent.pending_clarification = PendingClarification("原话", "command", 1)
        agent.pending_live_result = PendingLiveResult("live", (), "hint")
        agent.pending_retreat_prompt = True
        DeathService().handle_death(agent, make_time(), "寿元耗尽")
        self.assertEqual(agent.state.name, "dead")
        self.assertIsNone(agent.pending_encounter_id)
        self.assertIsNone(agent.pending_scenario)
        self.assertIsNone(agent.pending_clarification)
        self.assertIsNone(agent.pending_live_result)
        self.assertFalse(agent.pending_retreat_prompt)

    def test_reincarnate_keeps_partial_aptitude_and_insight(self):
        agent = make_agent(aptitude=1.6, insight=0.4)
        agent.state = __import__("model.domain.states", fromlist=["DeadState"]).DeadState()
        DeathService().reincarnate(agent)
        self.assertEqual(agent.state.name, "idle")
        self.assertAlmostEqual(agent.aptitude, 1.3)
        self.assertAlmostEqual(agent.insight, 0.2)
        self.assertEqual(agent.age, 6)
        self.assertEqual(agent.realm, "凡人")


class PlayTurnDeathTests(unittest.TestCase):
    def test_exhausting_lifespan_on_a_command_enters_dead_state(self):
        events = InMemoryEventRepository({"eat": _eat()})
        play_turn = make_play_turn(events)
        agent = make_agent(money=10, lifespan_left=1.0 / SHICHEN_PER_YEAR / 2)
        result = play_turn.handle_player_text(agent, make_tavern_world(), "吃饭")
        self.assertEqual(agent.state.name, "dead")
        self.assertIn("转世", result.freeform_narrative or "")

    def test_rebirth_choice_resumes_play(self):
        events = InMemoryEventRepository({"eat": _eat()})
        play_turn = make_play_turn(events)
        agent = make_agent(money=10, lifespan_left=1.0 / SHICHEN_PER_YEAR / 2, aptitude=1.4)
        play_turn.handle_player_text(agent, make_tavern_world(), "吃饭")
        result = play_turn.handle_player_text(agent, make_tavern_world(), "转世")
        self.assertEqual(agent.state.name, "idle")
        self.assertIn("转世", result.freeform_narrative or "")
        self.assertGreater(agent.aptitude, 1.0)


class RetreatConfirmTests(unittest.TestCase):
    def test_casual_duration_asks_for_confirmation(self):
        from model.services.clock_service import RetreatService
        from model.services.event_bus import InProcessEventBus
        from tests.helpers import make_play_turn as _make

        events = InMemoryEventRepository({})
        bus = InProcessEventBus()
        clock = GameClock(start=make_time(), bus=bus)
        retreat = RetreatService(clock, make_balance(), log=None)
        play_turn = _make(events, bus=bus, clock=clock)
        play_turn.retreat = retreat
        play_turn.balance = make_balance()
        agent = make_agent()
        play_turn.handle_player_text(agent, make_tavern_world(), "闭关")
        result = play_turn.handle_player_text(agent, make_tavern_world(), "随便")
        self.assertTrue(agent.pending_retreat_prompt)
        self.assertIn("确定的话直接说年数", result.freeform_narrative or "")


if __name__ == "__main__":
    unittest.main()
