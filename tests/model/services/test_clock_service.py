import random
import unittest

from model.repositories.event_log import InMemoryEventLogStore
from model.services.clock_service import GameClock, RetreatService
from tests.helpers import make_agent, make_balance, make_time, make_world


class RetreatServiceTests(unittest.TestCase):
    def test_lifespan_spent_matches_shichen_advanced(self):
        clock = GameClock(start=make_time())
        log = InMemoryEventLogStore()
        retreat = RetreatService(clock, make_balance(), random.Random(1), log=log)
        agent = make_agent(lifespan_left=80.0, cultivation=0.0)
        world = make_world()

        results = retreat.run(agent, world, target_shichen=24)  # 2 天，闭关 100 年 = 寿元 -100 的折算

        total_spent = sum(r.lifespan_spent for r in results)
        self.assertAlmostEqual(agent.lifespan_left, 80.0 - total_spent, places=6)
        self.assertGreater(agent.cultivation, 0.0)
        self.assertEqual(len(log._entries), len(results))  # 每批都走 apply_agent_diff + 记日志

    def test_tidal_day_bonus_applied_once_per_crossing(self):
        # 起点刚好在潮汐日前一天，闭关一批（12 时辰=1天）跨过初一，应该拿到潮汐加成，
        # 且不会因为按时辰细分而被重复结算。
        start = make_time(month=2, day=30, shichen=0)
        clock = GameClock(start=start)
        retreat = RetreatService(clock, make_balance(), random.Random(1))
        agent = make_agent(lifespan_left=80.0)
        world = make_world()

        results = retreat.run(agent, world, target_shichen=12)

        cfg = make_balance().cultivation_rate
        expected_no_bonus = cfg["base_per_shichen"] * cfg["qi_density_weight"] * 1.0 * 12
        self.assertGreater(results[0].cultivation_gained, expected_no_bonus)

    def test_lifespan_exhausted_interrupts_immediately(self):
        clock = GameClock(start=make_time())
        retreat = RetreatService(clock, make_balance(), random.Random(1))
        agent = make_agent(lifespan_left=0.5)  # 不到一批就耗尽
        world = make_world()

        results = retreat.run(agent, world, target_shichen=1200)

        self.assertTrue(results[-1].interrupted_by_force)
        self.assertEqual(results[-1].force_reason, "寿元耗尽")

    def test_settle_leaves_closed_door_when_no_pending(self):
        clock = GameClock(start=make_time())
        retreat = RetreatService(clock, make_balance(), random.Random(1))
        agent = make_agent(lifespan_left=80.0)
        world = make_world()
        retreat.run(agent, world, target_shichen=12)
        self.assertEqual(agent.state.name, "idle")  # settle() 落回 idle，不是停在 closed_door


class GameClockTests(unittest.TestCase):
    def test_advance_for_updates_agent_time_anchor(self):
        clock = GameClock(start=make_time(shichen=0))
        agent = make_agent()
        before = agent.time_anchor.current_game_time
        clock.advance_for(agent, 5)
        self.assertEqual(agent.time_anchor.current_game_time.shichen_until(before), -5)

    def test_advance_for_publishes_time_pass_event(self):
        from model.domain.system_events import TimePassEvent
        from model.services.event_bus import InProcessEventBus

        bus = InProcessEventBus()
        received = []
        bus.subscribe(TimePassEvent, lambda e: received.append(e))
        clock = GameClock(start=make_time(), bus=bus)
        agent = make_agent()
        clock.advance_for(agent, 3)
        self.assertEqual(len(received), 1)


if __name__ == "__main__":
    unittest.main()
