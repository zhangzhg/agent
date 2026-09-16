"""tests/model/repositories/test_live_event_pruning.py — 实时创作事件的容量回收
（README §6.1 P1-5）。

每一句没被识别的玩家输入都会创作一条永久的 live_ 事件，原本只增不减：录入编辑器
的事件列表会被玩家碎碎念淹没，向量兜底每回合装载的命令池也越滚越大。这里钉住
回收行为，以及"绝不能删出悬空引用"这条硬约束。
"""
import sqlite3
import unittest

from model.domain.events import LIVE_EVENT_ID_PREFIX, EventVariant, GameEventDef
from model.repositories.sqlite_event_repository import InMemoryEventRepository, SqliteEventRepository


def _event(event_id: str) -> GameEventDef:
    return GameEventDef(
        event_id=event_id,
        applicable_locations=("*",),
        applicable_time=None,
        predicate=None,
        weight=1.0,
        duration_shichen=1,
        cooldown_shichen=0,
        max_trigger_per_agent=None,
        exclusive_tags=(),
        priority=5,
        tags=(),
        aliases=(),
        result_pool=(),
        variants=(EventVariant("文案。"),),
        is_command=True,
        is_draft=False,
    )


class _PruningContract:
    """两种仓库实现共用同一套断言——InMemory 是测试替身，语义漂了测试就白测。"""

    def _repo(self):
        raise NotImplementedError

    def _ids(self):
        raise NotImplementedError

    def test_prunes_oldest_live_events_down_to_keep(self):
        repo = self._repo()
        for i in range(10):
            repo.save_event_def(_event(f"{LIVE_EVENT_ID_PREFIX}{i:02d}"))

        removed = repo.prune_live_events(keep=4)

        self.assertEqual(removed, 6)
        remaining = sorted(self._ids())
        self.assertEqual(remaining, [f"{LIVE_EVENT_ID_PREFIX}{i:02d}" for i in range(6, 10)])

    def test_handmade_events_are_never_pruned(self):
        repo = self._repo()
        for i in range(5):
            repo.save_event_def(_event(f"seeded_{i}"))
        for i in range(5):
            repo.save_event_def(_event(f"{LIVE_EVENT_ID_PREFIX}{i}"))

        repo.prune_live_events(keep=1)

        remaining = set(self._ids())
        self.assertTrue({f"seeded_{i}" for i in range(5)}.issubset(remaining))

    def test_protected_ids_survive_even_when_old(self):
        """挂起中的事件被删掉 = 悬空引用，玩家会卡在一个查不到定义的挂起态上。"""
        repo = self._repo()
        for i in range(10):
            repo.save_event_def(_event(f"{LIVE_EVENT_ID_PREFIX}{i:02d}"))

        repo.prune_live_events(keep=2, protected_ids={f"{LIVE_EVENT_ID_PREFIX}00"})

        remaining = set(self._ids())
        self.assertIn(f"{LIVE_EVENT_ID_PREFIX}00", remaining)

    def test_no_op_when_under_limit(self):
        repo = self._repo()
        for i in range(3):
            repo.save_event_def(_event(f"{LIVE_EVENT_ID_PREFIX}{i}"))
        self.assertEqual(repo.prune_live_events(keep=10), 0)
        self.assertEqual(len(self._ids()), 3)


class SqlitePruningTests(_PruningContract, unittest.TestCase):
    def _repo(self):
        self.conn = sqlite3.connect(":memory:")
        self.repo = SqliteEventRepository(self.conn)
        return self.repo

    def _ids(self):
        return [r[0] for r in self.conn.execute("SELECT event_id FROM event_defs")]


class InMemoryPruningTests(_PruningContract, unittest.TestCase):
    def _repo(self):
        self.repo = InMemoryEventRepository()
        return self.repo

    def _ids(self):
        return list(self.repo._events)


if __name__ == "__main__":
    unittest.main()
