"""tests/test_npc_schedule_wiring.py — 端到端验证 bootstrap.py 里新接的
ScheduleService/NPC 巡检线路（README 1.5.2）。

单元测试（test_schedule_service.py）验证的是 ScheduleService 自己的契约；这里
额外验证"真实接线"本身没接错——TimePassEvent 发布后，agents_provider 真的能从
agent_repo 里筛出 is_npc 的 Agent，executor 真的走 PlayTurnService.trigger 并把
结果存回去，而且重复 load() 是幂等的（agent_repository.py 的 at 时间戳 bug 曾经
在这条真实链路上被复现过：NPC 修为在 40 个时辰内滚到 400+）。
"""
import unittest

from bootstrap import build_app
from content.npc import SECT_DISCIPLE_ID, TAVERN_KEEPER_ID
from content.seed import seed_all
from content.session import ensure_seed_agent


class NpcScheduleWiringTests(unittest.TestCase):
    def setUp(self):
        self.app = build_app(rng_seed=42)
        seed_all(self.app)
        self.player = ensure_seed_agent(self.app, "player")

    def test_seeded_npcs_are_marked_and_listed(self):
        npcs = {a.agent_id for a in self.app.agent_repo.list_all() if a.is_npc}
        self.assertEqual(npcs, {TAVERN_KEEPER_ID, SECT_DISCIPLE_ID})

    def test_advancing_the_clock_eventually_changes_npc_state(self):
        before = self.app.agent_repo.load(SECT_DISCIPLE_ID)
        for _ in range(60):
            self.app.clock.advance_for(self.player, 1)
        after = self.app.agent_repo.load(SECT_DISCIPLE_ID)

        # 不断言具体数值（随机接龙，不该在测试里锁死具体抽中哪条事件）；
        # 只断言"日程巡检确实让 NPC 的状态动了"，这正是接线要交付的东西。
        self.assertNotEqual(
            (before.cultivation, before.money, tuple(before.flags), len(before.causes)),
            (after.cultivation, after.money, tuple(after.flags), len(after.causes)),
        )

    def test_repeated_reload_after_ticks_is_idempotent(self):
        """agent_repository.py 的 at 时间戳 bug 的直接回归：不该重复 load 就继续涨。"""
        for _ in range(60):
            self.app.clock.advance_for(self.player, 1)

        first = self.app.agent_repo.load(SECT_DISCIPLE_ID)
        second = self.app.agent_repo.load(SECT_DISCIPLE_ID)
        third = self.app.agent_repo.load(SECT_DISCIPLE_ID)

        self.assertEqual(first.cultivation, second.cultivation)
        self.assertEqual(second.cultivation, third.cultivation)
        self.assertEqual(first.money, third.money)

    def test_non_idle_npc_is_skipped_by_schedule(self):
        """acting/挂起态的 NPC 不该被日程巡检打断（README 1.7 仲裁分级）。"""
        from model.domain.states import ClosedDoorState

        disciple = self.app.agent_repo.load(SECT_DISCIPLE_ID)
        disciple.state = ClosedDoorState()
        self.app.agent_repo.save(disciple)

        for _ in range(20):
            self.app.clock.advance_for(self.player, 1)

        still_closed = self.app.agent_repo.load(SECT_DISCIPLE_ID)
        self.assertEqual(still_closed.state.name, "closed_door")


if __name__ == "__main__":
    unittest.main()
