"""tests/test_content_pack.py — 内容库完整性自检（README §6.3 录入自检清单
的一部分，用测试固化下来而不是只靠人工过一遍）。

之前没有任何测试覆盖 content/ 下的实际数据，一条真实 bug 就藏在这里：apprentice
拜师成功只写了 CauseLink，没有 FlagSet("有门派归属")，导致 cangjian.py 里四条
以这个 flag 为门槛的事件永远进不了合格池——拜了个寂寞。这个测试把"某个 FLAG
谓词有没有对应的 FlagSet 结果"这件事一般化，不止防这一个 bug 重现。
"""
from __future__ import annotations

import unittest

from content.items import ALL as ALL_ITEMS
from content.map import build_mvp_world
from content.seed import ALL_EVENTS
from model.domain.predicates import Predicate, PredicateGroup, PredicateType
from model.domain.results import Check, FlagSet


def _iter_predicates(p):
    if p is None:
        return
    if isinstance(p, PredicateGroup):
        for item in p.items:
            yield from _iter_predicates(item)
    else:
        yield p


def _iter_flag_sets(results) -> "set[str]":
    """递归收集 result_pool 里所有 FlagSet 的 name——包括嵌在 Check.on_success/
    on_fail 里的（Check 本身不是叶子结果，得展开）。"""
    names: set[str] = set()
    for r in results:
        if isinstance(r, FlagSet):
            names.add(r.name)
        elif isinstance(r, Check):
            names |= _iter_flag_sets(r.on_success)
            names |= _iter_flag_sets(r.on_fail)
    return names


class ContentPackIntegrityTests(unittest.TestCase):
    def test_no_duplicate_event_ids(self):
        seen: dict[str, int] = {}
        for e in ALL_EVENTS:
            seen[e.event_id] = seen.get(e.event_id, 0) + 1
        duplicates = {k: v for k, v in seen.items() if v > 1}
        self.assertEqual(duplicates, {}, f"重复的 event_id：{duplicates}")

    def test_no_duplicate_item_ids(self):
        seen: dict[str, int] = {}
        for item in ALL_ITEMS:
            seen[item.item_id] = seen.get(item.item_id, 0) + 1
        duplicates = {k: v for k, v in seen.items() if v > 1}
        self.assertEqual(duplicates, {}, f"重复的 item_id：{duplicates}")

    def test_item_drops_reference_known_items(self):
        """事件掉落的物品必须先在 content/items.py 里定义过，否则背包面板拿到一个
        查不到名字/描述的 item_id（README §3.2）。"""
        from model.domain.results import ItemConsume, ItemDrop

        known_ids = {item.item_id for item in ALL_ITEMS}
        missing: list[str] = []

        def _walk(results, event_id: str) -> None:
            for r in results:
                if isinstance(r, (ItemDrop, ItemConsume)) and r.item_id not in known_ids:
                    missing.append(f"{event_id} -> {r.item_id}")
                elif isinstance(r, Check):
                    _walk(r.on_success, event_id)
                    _walk(r.on_fail, event_id)

        for e in ALL_EVENTS:
            _walk(e.result_pool, e.event_id)
            for ro in e.reply_options:
                _walk(ro.results, e.event_id)

        self.assertEqual(missing, [], f"引用了未登记的物品：{missing}")

    def test_chain_event_references_point_to_existing_events(self):
        """ChainEvent / ReplyOption.chain_event_id 打错字会让连锁在运行时静默消失
        （EventRegistry 里 get_by_id 返回 None，PlayTurnService 直接不处理）。"""
        from model.domain.results import ChainEvent

        known_ids = {e.event_id for e in ALL_EVENTS}
        missing: list[str] = []

        def _walk(results, event_id: str) -> None:
            for r in results:
                if isinstance(r, ChainEvent) and r.event_id not in known_ids:
                    missing.append(f"{event_id} -> {r.event_id}")
                elif isinstance(r, Check):
                    _walk(r.on_success, event_id)
                    _walk(r.on_fail, event_id)

        for e in ALL_EVENTS:
            _walk(e.result_pool, e.event_id)
            for ro in e.reply_options:
                _walk(ro.results, e.event_id)
                if ro.chain_event_id is not None and ro.chain_event_id not in known_ids:
                    missing.append(f"{e.event_id} (reply) -> {ro.chain_event_id}")

        self.assertEqual(missing, [], f"连锁事件引用了不存在的 event_id：{missing}")

    def test_applicable_locations_match_a_real_location_type(self):
        """"*" 或某个在 MVP 世界里真实存在的地点类型；写错字会让事件永远进不了
        任何合格池，静默变成死代码（README §6.3 自检清单第一条）。"""
        world = build_mvp_world()
        known_types = {loc.location_type for loc in world.locations.values()}
        bad: list[str] = []
        for e in ALL_EVENTS:
            for loc_type in e.applicable_locations:
                if loc_type != "*" and loc_type not in known_types:
                    bad.append(f"{e.event_id} -> {loc_type!r}")
        self.assertEqual(bad, [], f"引用了不存在的地点类型：{bad}")

    def test_every_flag_predicate_has_a_reachable_flag_set(self):
        """回归 + 一般化：每个作为门槛使用的 FLAG，事件库里至少要有一条结果能
        真的置位它，否则这个门槛永远打不开（apprentice 漏 FlagSet 就是这么废的）。"""
        required_flags: set[str] = set()
        for e in ALL_EVENTS:
            for p in _iter_predicates(e.predicate):
                if isinstance(p, Predicate) and p.type is PredicateType.FLAG:
                    required_flags.add(p.args[0])

        settable_flags: set[str] = set()
        for e in ALL_EVENTS:
            settable_flags |= _iter_flag_sets(e.result_pool)
            for ro in e.reply_options:
                settable_flags |= _iter_flag_sets(ro.results)

        unreachable = required_flags - settable_flags
        self.assertEqual(unreachable, set(), f"这些 FLAG 门槛没有任何结果能置位：{unreachable}")

    def test_apprentice_success_grants_sect_affiliation_flag(self):
        """具体场景的直接回归：拜师成功必须真的拿到"有门派归属"，藏剑山门那四条
        事件（sect_training/elder_insight/sect_rivalry/mountain_gate_test）才摸得到。"""
        apprentice = next(e for e in ALL_EVENTS if e.event_id == "apprentice")
        check = next(r for r in apprentice.result_pool if isinstance(r, Check))
        granted = _iter_flag_sets(check.on_success)
        self.assertIn("有门派归属", granted)


if __name__ == "__main__":
    unittest.main()
