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
        # now_provider 必须来自全局时钟而非某个 Agent 自己的 time_anchor（见
        # agent_repository.py 的说明）；这里所有测试用的 Agent 都是刚 make_agent()
        # 出来、锚点未被推进过的，值恰好等于 make_time()，跟旧行为一致。
        self.repo = SqliteAgentRepository(self.snapshots, self.log, now_provider=make_time)

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

    def test_every_pending_dataclass_field_survives_round_trip(self):
        """结构性回归测试：三个挂起态 dataclass 的**每一个字段**都必须原样活过
        存盘/读档。以前 codec 是逐字段手抄的（AppliedDiff 和 Agent 两侧各抄一遍，
        共六处），漏抄一处的后果是"读档静默丢状态"、没有任何报错。现在 codec 按
        `dataclasses.fields` 自动展开，这条测试则从外部盯住结果：以后给任何一个
        挂起态 dataclass 加字段，忘了处理就会在这里红。"""
        from dataclasses import fields as dc_fields

        from model.domain.agent import PendingClarification, PendingLiveResult, PendingScenario

        agent = make_agent()
        agent.pending_scenario = PendingScenario("sc1", "node_a", "host_evt")
        agent.pending_clarification = PendingClarification("原话", "command", 2)
        agent.pending_live_result = PendingLiveResult(
            event_id="live_abc",
            deferred_result_pool=({"kind": "state_change", "field": "money", "delta": -3.0},),
            narrative_hint="埋了个伏笔",
            attempts=1,
        )
        self.repo.save(agent)

        reloaded = self.repo.load("A")

        for attr in ("pending_scenario", "pending_clarification", "pending_live_result"):
            original, restored = getattr(agent, attr), getattr(reloaded, attr)
            self.assertIsNotNone(restored, f"{attr} 整个丢了")
            for f in dc_fields(original):
                with self.subTest(pending=attr, field=f.name):
                    self.assertEqual(
                        getattr(restored, f.name), getattr(original, f.name),
                        f"{attr}.{f.name} 没能原样读回来",
                    )

    def test_pending_live_result_pool_is_restored_as_tuple(self):
        """frozen dataclass 里放 list 会破坏可哈希性、也跟运行时构造的实例不等价，
        JSON 反序列化必须还原成 tuple。"""
        from model.domain.agent import PendingLiveResult

        agent = make_agent()
        agent.pending_live_result = PendingLiveResult(
            "live_x", ({"kind": "state_change", "field": "money", "delta": 1.0},), "hint"
        )
        self.repo.save(agent)

        restored = self.repo.load("A").pending_live_result
        self.assertIsInstance(restored.deferred_result_pool, tuple)

    def test_unknown_keys_in_saved_pending_state_are_ignored(self):
        """旧存档里可能带着已经删掉的字段——多余的键应该被忽略，而不是让
        dataclass 构造炸掉、整个存档读不回来。"""
        from model.domain.agent import PendingScenario
        from model.repositories.codec import _pending_from_json

        restored = _pending_from_json(
            {"scenario_id": "s", "current_node_id": "n", "host_event_id": "h", "早就删掉的字段": 1},
            PendingScenario,
        )
        self.assertEqual(restored.scenario_id, "s")

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

    def test_replay_restores_event_history_from_applied_diff(self):
        from model.domain.diff import HistoryRecord

        agent = make_agent()
        self.repo.save(agent)
        later = make_time().add_shichen(3)
        occ = GameEventOccurrence(
            "eat", TriggerSource.PLAYER, "A", later, 0,
            applied_diff=AppliedDiff(
                history_records=(HistoryRecord("eat", later, ("生活",), 0, cooldown_shichen=6),),
                attr_deltas=(("money", -2.0),),
            ),
        )
        self.log.append(occ)
        reloaded = self.repo.load("A")
        self.assertEqual(reloaded.event_history.trigger_count("eat"), 1)
        self.assertEqual(reloaded.money, 8)

    def test_save_drops_log_rows_already_baked_into_the_snapshot(self):
        agent = make_agent(money=10)
        now = make_time()
        occ = GameEventOccurrence(
            "eat", TriggerSource.PLAYER, "A", now, 0,
            applied_diff=AppliedDiff(attr_deltas=(("money", -1.0),)),
        )
        self.log.append(occ)
        agent.money -= 1
        self.repo.save(agent)
        remaining = self.conn.execute("SELECT COUNT(*) FROM event_log").fetchone()[0]
        self.assertEqual(remaining, 0)
        self.assertEqual(self.repo.load("A").money, 9)


if __name__ == "__main__":
    unittest.main()
