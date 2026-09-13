"""tests/model/repositories/test_snapshot_growth.py — 快照存储的增长边界。

背景（优化建议.md P0-2）：每回合会写 1~2 份**全量**快照（世界 + 全部 Agent），
原本既不裁剪历史行、世界没变也照写不误。一局 1440 轮的对话能滚出约 2900 行、
几百 MB。这里把两条止血措施钉住：过期快照会被裁掉、世界没变就不写盘。
"""
import sqlite3
import unittest

from model.domain.map import Location, LocationKind
from model.repositories.snapshot_store import SqliteSnapshotStore
from model.repositories.world_repository import SqliteWorldRepository
from tests.helpers import make_time


class SnapshotRetentionTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")

    def _rows(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]

    def test_old_snapshots_are_pruned_to_retention_limit(self):
        store = SqliteSnapshotStore(self.conn, retention=5)
        for i in range(30):
            store.save_snapshot({"n": i}, make_time())
        self.assertEqual(self._rows(), 5)

    def test_latest_snapshot_is_the_one_kept(self):
        """裁剪必须只砍旧的——load_latest_snapshot() 是全项目唯一的快照读取点，
        砍错方向等于直接丢档。"""
        store = SqliteSnapshotStore(self.conn, retention=3)
        for i in range(10):
            store.save_snapshot({"n": i}, make_time())
        payload, _at = store.load_latest_snapshot()
        self.assertEqual(payload["n"], 9)

    def test_retention_of_one_keeps_working(self):
        store = SqliteSnapshotStore(self.conn, retention=1)
        store.save_snapshot({"n": 1}, make_time())
        store.save_snapshot({"n": 2}, make_time())
        self.assertEqual(self._rows(), 1)
        self.assertEqual(store.load_latest_snapshot()[0]["n"], 2)


class WorldSaveDirtyCheckTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.store = SqliteSnapshotStore(self.conn)
        self.repo = SqliteWorldRepository(self.store)

    def _rows(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]

    def test_unchanged_world_is_not_written_again(self):
        self.repo.assemble_view()
        self.repo.save(make_time())
        after_first = self._rows()
        for _ in range(10):
            self.repo.save(make_time())
        self.assertEqual(self._rows(), after_first)

    def test_changed_world_is_written(self):
        view = self.repo.assemble_view()
        self.repo.save(make_time())
        before = self._rows()
        view.mutable_state().locations["x"] = Location("x", "新地点", LocationKind.CITY, "城市")
        self.repo.save(make_time())
        self.assertEqual(self._rows(), before + 1)

    def test_reverting_a_change_is_detected_as_unchanged(self):
        """脏判定用 sort_keys 的稳定序列化，不受 dict 插入顺序影响。"""
        view = self.repo.assemble_view()
        state = view.mutable_state()
        state.locations["x"] = Location("x", "新地点", LocationKind.CITY, "城市")
        self.repo.save(make_time())
        before = self._rows()
        del state.locations["x"]
        self.repo.save(make_time())  # 变了，要写
        state.locations["x"] = Location("x", "新地点", LocationKind.CITY, "城市")
        self.repo.save(make_time())  # 又变回去了，也要写（内容确实不同于上一次落盘）
        self.assertEqual(self._rows(), before + 2)
        self.repo.save(make_time())  # 这次没变，不该写
        self.assertEqual(self._rows(), before + 2)

    def test_world_survives_agent_only_saves(self):
        """世界跳过写盘是安全的前提：agent_repository.save() 会把 latest payload
        整个复制一份再改 agents 键，world 键被原样带到新行上。这条测试盯住这个
        前提——它一旦不成立，跳过写盘就会丢世界数据。"""
        from model.repositories.agent_repository import SqliteAgentRepository
        from model.repositories.event_log import SqliteEventLogStore
        from tests.helpers import make_agent

        view = self.repo.assemble_view()
        view.mutable_state().locations["x"] = Location("x", "新地点", LocationKind.CITY, "城市")
        self.repo.save(make_time())

        agents = SqliteAgentRepository(self.store, SqliteEventLogStore(self.conn), now_provider=make_time)
        for _ in range(5):
            agents.save(make_agent(agent_id="player"))

        payload, _at = self.store.load_latest_snapshot()
        self.assertIn("x", payload["world"]["locations"])


if __name__ == "__main__":
    unittest.main()
