import logging
import sqlite3
import unittest

from model.domain.diff import AppliedDiff
from model.domain.events import GameEventOccurrence, TriggerSource
from model.repositories.agent_repository import SqliteAgentRepository
from model.repositories.event_log import SqliteEventLogStore
from model.repositories.snapshot_store import SqliteSnapshotStore
from tests.helpers import make_agent, make_time


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.snapshots = SqliteSnapshotStore(self.conn)
        self.log = SqliteEventLogStore(self.conn)
        self.repo = SqliteAgentRepository(self.snapshots, self.log)

    def test_load_after_snapshot_reproduces_saved_state(self):
        agent = make_agent(money=10, satiety=50)
        self.repo.save(agent)
        reloaded = self.repo.load("A")
        self.assertEqual(reloaded.money, 10)
        self.assertEqual(reloaded.satiety, 50)
        self.assertEqual(reloaded.state.name, "idle")

    def test_pending_fields_and_history_survive_round_trip(self):
        agent = make_agent()
        agent.pending_encounter_id = "fish"
        agent.event_history.record("eat", make_time(), ("生活",), 0)
        self.repo.save(agent)

        reloaded = self.repo.load("A")

        self.assertEqual(reloaded.pending_encounter_id, "fish")
        self.assertEqual(reloaded.event_history.trigger_count("eat"), 1)

    def test_zero_duration_event_at_snapshot_boundary_is_not_replayed_twice(self):
        """回归测试：save() 用 agent 当前时刻当 `at`；如果一条事件 duration_shichen=0
        （时钟压根没往前挪，occurred_at 恰好等于快照时刻），下一次 load() 不该把它
        的 diff 重放第二遍。这曾经是真实 bug（金龙鱼这类 needs_reply 链式事件，两段
        都是 0 时长，money 会在每次 load() 时被反复多扣一次）。"""
        agent = make_agent(money=10)
        now = agent.time_anchor.current_game_time  # duration_shichen=0：时间不推进
        occ = GameEventOccurrence(
            "buy", TriggerSource.PLAYER, "A", now, 0,
            applied_diff=AppliedDiff(attr_deltas=(("money", -20.0),)),
        )
        self.log.append(occ)
        agent.money -= 20  # 模拟本轮已经在内存里应用过这条 diff（正常对局流程如此）
        self.repo.save(agent)  # 快照时刻 == occ.occurred_at

        reloaded_once = self.repo.load("A")
        self.assertEqual(reloaded_once.money, -10)  # 10 - 20，只应用一次

        # 再 load 一次（模拟下一回合的 ChatController.on_player_message 开头）：
        # 不应该再扣一次 20。
        reloaded_twice = self.repo.load("A")
        self.assertEqual(reloaded_twice.money, -10)

    def test_replay_since_snapshot_reconstructs_later_diffs(self):
        agent = make_agent(money=10)
        self.repo.save(agent)  # 快照：money=10

        # 快照之后又发生了一条事件（模拟同一局里 save() 之间的多次结算）
        later = make_time().add_shichen(5)
        occ = GameEventOccurrence(
            "spend", TriggerSource.PLAYER, "A", later, 0,
            applied_diff=AppliedDiff(attr_deltas=(("money", -4.0),)),
        )
        self.log.append(occ)

        reloaded = self.repo.load("A")
        self.assertEqual(reloaded.money, 6.0)  # 10 - 4，来自重放而不是快照本身

    def test_corrupt_log_entry_without_applied_diff_is_skipped(self):
        agent = make_agent(money=10)
        self.repo.save(agent)
        # 直接插入一条缺 applied_diff 的坏日志（绕过 append() 的拒绝逻辑，模拟历史脏数据）。
        # ordinal 必须 >= 快照时刻，否则 replay_since() 的时间过滤会先把它挡在外面，
        # 根本走不到"缺 applied_diff 就跳过并告警"这条分支。
        import json

        # replay_since 是严格大于快照时刻（见 event_log.py 的说明），所以坏日志得
        # 排在快照时刻*之后*才会被 load() 实际扫到、进而触发"缺 applied_diff 跳过"分支。
        corrupt_ordinal = agent.time_anchor.current_game_time._ordinal() + 1
        self.conn.execute(
            "INSERT INTO event_log (ordinal, payload) VALUES (?, ?)",
            (corrupt_ordinal, json.dumps({
                "event_id": "corrupt", "trigger_source": "player", "agent_id": "A",
                "occurred_at": {"epoch": "太乙历", "year": 100, "month": 1, "day": 1, "shichen": 6},
                "chosen_variant_index": 0, "applied_diff": None, "world_diff": None, "def_schema_version": 1,
            })),
        )
        self.conn.commit()

        with self.assertLogs("eventhorizon.event_log", level="WARNING"):
            reloaded = self.repo.load("A")
        self.assertEqual(reloaded.money, 10)  # 坏日志被跳过，不污染重放结果

    def test_append_refuses_occurrence_without_applied_diff(self):
        occ = GameEventOccurrence("e", TriggerSource.PLAYER, "A", make_time(), 0, applied_diff=None)
        with self.assertLogs("eventhorizon.event_log", level="WARNING"):
            self.log.append(occ)
        self.assertEqual(self.log.replay_since(make_time().add_shichen(-1)), [])


if __name__ == "__main__":
    unittest.main()
