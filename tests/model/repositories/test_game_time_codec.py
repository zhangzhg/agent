"""tests/model/repositories/test_game_time_codec.py — GameTime 存档压缩。

旧格式每个时刻约 70 字节的对象；新格式是一个整数。读档必须两种都认，否则
换格式等于把玩家存档毁掉、这一局接不下去。
"""
import json
import sqlite3
import unittest

from model.domain.agent import AgentEventHistory
from model.domain.time import GameTime
from model.repositories.codec import agent_from_dict, agent_to_dict, game_time_from_dict, game_time_to_dict
from model.repositories.snapshot_store import SqliteSnapshotStore
from tests.helpers import make_agent, make_time


_OLD_WIRE = {"epoch": "太乙历", "year": 100, "month": 1, "day": 1, "shichen": 6}


class GameTimeWireFormatTests(unittest.TestCase):
    def test_new_writes_are_integers(self):
        t = make_time()
        wire = game_time_to_dict(t)
        self.assertIsInstance(wire, int)
        self.assertEqual(game_time_from_dict(wire), t)

    def test_old_object_format_still_loads(self):
        restored = game_time_from_dict(_OLD_WIRE)
        self.assertEqual(restored, make_time())

    def test_snapshot_at_column_old_json_still_loads(self):
        conn = sqlite3.connect(":memory:")
        store = SqliteSnapshotStore(conn)
        conn.execute(
            "INSERT INTO snapshots (at, payload) VALUES (?, ?)",
            (json.dumps(_OLD_WIRE, ensure_ascii=False), json.dumps({"n": 1})),
        )
        conn.commit()
        payload, at = store.load_latest_snapshot()
        self.assertEqual(payload["n"], 1)
        self.assertEqual(at, make_time())

    def test_agent_history_old_times_survive_load(self):
        agent = make_agent()
        blob = agent_to_dict(agent)
        blob["time_anchor"]["last_synced_game_time"] = _OLD_WIRE
        blob["event_history"] = {
            "triggers": {"eat": [_OLD_WIRE]},
            "variant_cursor": {},
            "recent_tags": [["生活", _OLD_WIRE]],
            "exclusive_tag_expiry": {},
            "last_trigger_seq": {"eat": 1},
            "sequence": 1,
        }
        restored = agent_from_dict(blob)
        self.assertEqual(restored.time_anchor.last_synced_game_time, make_time())
        self.assertEqual(restored.event_history.trigger_count("eat"), 1)
        self.assertEqual(restored.event_history.recent_tags[0][1], make_time())

    def test_full_history_window_is_much_smaller_than_object_format(self):
        t = make_time()
        history = AgentEventHistory()
        for i in range(AgentEventHistory.MAX_TRIGGERS_PER_EVENT):
            history.record("eat", t.add_shichen(i), ("生活",), 0)
        for i in range(AgentEventHistory.TAG_QUOTA_WINDOW * 4):
            history.record(f"evt{i % 5}", t.add_shichen(i), ("奇遇",), 0)
        agent = make_agent(event_history=history)
        new_json = json.dumps(agent_to_dict(agent), ensure_ascii=False)

        old_blob = agent_to_dict(agent)
        old_hist = old_blob["event_history"]
        old_hist["triggers"] = {
            k: [{"epoch": "太乙历", "year": t.year, "month": t.month, "day": t.day, "shichen": t.shichen} for t in vs]
            for k, vs in history.triggers.items()
        }
        old_hist["recent_tags"] = [
            [tag, {"epoch": "太乙历", "year": t.year, "month": t.month, "day": t.day, "shichen": t.shichen}]
            for tag, t in history.recent_tags
        ]
        old_json = json.dumps(old_blob, ensure_ascii=False)

        self.assertLess(len(new_json), len(old_json) // 3)
        self.assertEqual(agent_from_dict(json.loads(new_json)).event_history.trigger_count("eat"), 64)


if __name__ == "__main__":
    unittest.main()
