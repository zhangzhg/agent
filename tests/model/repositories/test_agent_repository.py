"""tests/model/repositories/test_agent_repository.py — list_all() 与快照时间戳
（README 1.5.2 日程巡检的读取面 + 一个真实复现过的多 Agent 数据损坏 bug）。
"""
import sqlite3
import unittest

from model.domain.diff import AppliedDiff, apply_agent_diff
from model.domain.events import GameEventOccurrence, TriggerSource
from model.domain.time import AgentTimeAnchor
from model.repositories.agent_repository import SqliteAgentRepository
from model.repositories.event_log import SqliteEventLogStore
from model.repositories.snapshot_store import SqliteSnapshotStore
from tests.helpers import make_agent, make_time


class _MutableClock:
    """让测试能显式控制"全局当前时刻"，独立于任何一个 Agent 自己的 time_anchor。"""

    def __init__(self, at) -> None:
        self.at = at

    def now(self):
        return self.at


class AgentRepositoryListAllTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.snapshots = SqliteSnapshotStore(self.conn)
        self.log = SqliteEventLogStore(self.conn)
        self.clock = _MutableClock(make_time())
        self.repo = SqliteAgentRepository(self.snapshots, self.log, now_provider=self.clock.now)

    def test_list_all_returns_every_saved_agent(self):
        self.repo.save(make_agent(agent_id="player", money=1))
        self.repo.save(make_agent(agent_id="npc_a", money=2))
        self.repo.save(make_agent(agent_id="npc_b", money=3))

        loaded = {a.agent_id: a.money for a in self.repo.list_all()}

        self.assertEqual(loaded, {"player": 1, "npc_a": 2, "npc_b": 3})

    def test_list_all_on_empty_repository_is_empty(self):
        self.assertEqual(self.repo.list_all(), [])

    def test_saving_one_agent_does_not_erase_another(self):
        self.repo.save(make_agent(agent_id="player", money=1))
        self.repo.save(make_agent(agent_id="npc_a", money=2))

        self.assertEqual(self.repo.load("player").money, 1)
        self.assertEqual(self.repo.load("npc_a").money, 2)


class SnapshotTimestampRegressionTests(unittest.TestCase):
    """回归测试：save() 曾经用 agent.time_anchor.current_game_time 当快照的 at。
    对一个只触发 duration_shichen=0 事件的 Agent（典型的日程巡检 NPC，锚点永远
    停在出生时刻），这会让下次 load() 的 replay_since(at) 把它自己从出生以来的
    全部历史重放一遍，diff 越滚越大——实测复现过修为在 40 个时辰内滚到 400+。
    现在 at 必须来自注入的全局 now_provider，不依赖任何单个 Agent 的锚点。"""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.snapshots = SqliteSnapshotStore(self.conn)
        self.log = SqliteEventLogStore(self.conn)
        # 全局时钟从一开始就领先所有 Agent 的出生时刻很多——这是关键前提：
        # 如果 save() 错误地退回去用某个 Agent 自己的（更早的）锚点当 at，
        # replay_since 就会把这个 Agent 的全部历史重新扫一遍。
        self.clock = _MutableClock(make_time(year=100))
        self.repo = SqliteAgentRepository(self.snapshots, self.log, now_provider=self.clock.now)

    def _apply_and_log_zero_duration_event(self, agent, event_id: str, money_delta: float) -> None:
        """模拟 PlayTurnService.execute_occurrence 对一条 duration_shichen=0 事件的
        处理：先在内存里 apply diff，再写日志，最后 save()——过程中 agent 自己的
        time_anchor 完全不动（因为 GameClock.advance_for(agent, 0) 是空操作）。"""
        diff = AppliedDiff(attr_deltas=(("money", money_delta),))
        apply_agent_diff(agent, diff)
        occ = GameEventOccurrence(event_id, TriggerSource.SCHEDULE, agent.agent_id, self.clock.at, 0, applied_diff=diff)
        self.log.append(occ)
        self.repo.save(agent)

    def test_repeated_zero_duration_triggers_do_not_compound_on_reload(self):
        # 出生锚点固定在比全局时钟早得多的一个时刻（对应 content/npc.py 的 NPC：
        # 出生于太乙历七十年，游戏当前在一百年），且此后永不推进——duration=0
        # 的事件不会碰它，这正是复现 bug 的关键前提。
        npc = make_agent(agent_id="npc", money=0, time_anchor=AgentTimeAnchor(last_synced_game_time=make_time(year=70)))
        birth_anchor = npc.time_anchor.current_game_time
        self.assertNotEqual(birth_anchor, self.clock.at)  # 前提：锚点确实落后于全局时钟

        self._apply_and_log_zero_duration_event(npc, "chore_1", +5.0)
        self._apply_and_log_zero_duration_event(npc, "chore_2", +7.0)

        first_load = self.repo.load("npc")
        second_load = self.repo.load("npc")
        third_load = self.repo.load("npc")

        self.assertEqual(first_load.money, 12.0)
        self.assertEqual(second_load.money, 12.0)  # 重复 load 不应该让钱继续涨
        self.assertEqual(third_load.money, 12.0)

    def test_interleaved_saves_across_two_stalled_agents_stay_isolated(self):
        """两个 NPC 交替触发 0 时长事件、交替 save()——各自的重放不该污染对方，
        也不该在自己身上滚雪球。"""
        early_anchor = AgentTimeAnchor(last_synced_game_time=make_time(year=70))
        a = make_agent(agent_id="npc_a", money=0, time_anchor=early_anchor)
        b = make_agent(agent_id="npc_b", money=0, time_anchor=AgentTimeAnchor(last_synced_game_time=make_time(year=70)))

        self._apply_and_log_zero_duration_event(a, "a1", +10.0)
        self._apply_and_log_zero_duration_event(b, "b1", +100.0)
        self._apply_and_log_zero_duration_event(a, "a2", +10.0)
        self._apply_and_log_zero_duration_event(b, "b1", +100.0)

        self.assertEqual(self.repo.load("npc_a").money, 20.0)
        self.assertEqual(self.repo.load("npc_b").money, 200.0)
        # 再多 load 几轮，确认不会继续变化（幂等）
        for _ in range(3):
            self.assertEqual(self.repo.load("npc_a").money, 20.0)
            self.assertEqual(self.repo.load("npc_b").money, 200.0)


if __name__ == "__main__":
    unittest.main()
