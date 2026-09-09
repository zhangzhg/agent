"""tests/model/services/test_exploration_service.py — 神识扫描（GAME_DESIGN §5.3）。

之前完全没有测试覆盖——exploration_service.py 存在于仓库里，但没人验证过它还能
不能跑（audit 发现的"写了但没测"缺口之一）。
"""
import unittest

from model.domain.map import Location, LocationKind, WorldState, WorldView
from model.services.exploration_service import scan_for_hidden_locations


class _FixedRng:
    def __init__(self, roll: float) -> None:
        self._roll = roll

    def random(self) -> float:
        return self._roll

    def choice(self, seq):
        return seq[0]


def _world_with_hidden(concealment: float) -> WorldView:
    state = WorldState(locations={
        "cangwu": Location("cangwu", "苍梧城", LocationKind.CITY, "城市"),
        "guixu": Location(
            "guixu", "归墟秘境", LocationKind.SECRET_REALM, "秘境",
            parent_location_id="cangwu", hidden=True, concealment=concealment,
        ),
    })
    return WorldView(_state=state)


class ExplorationServiceTests(unittest.TestCase):
    def test_hit_marks_location_discovered_and_names_it(self):
        world = _world_with_hidden(concealment=0.9)
        result = scan_for_hidden_locations("cangwu", world, _FixedRng(0.0))  # 0.0 < 0.9 → 命中

        self.assertEqual(result.found_location_id, "guixu")
        self.assertIn("归墟秘境", result.narrative)
        self.assertTrue(world.mutable_state().get("guixu").discovered)

    def test_miss_gives_narration_without_discovering(self):
        world = _world_with_hidden(concealment=0.1)
        result = scan_for_hidden_locations("cangwu", world, _FixedRng(0.99))  # 0.99 >= 0.1 → 未命中

        self.assertIsNone(result.found_location_id)
        self.assertTrue(result.narrative)
        self.assertFalse(world.mutable_state().get("guixu").discovered)

    def test_already_discovered_location_is_not_a_candidate_again(self):
        state = WorldState(locations={
            "cangwu": Location("cangwu", "苍梧城", LocationKind.CITY, "城市"),
            "guixu": Location(
                "guixu", "归墟秘境", LocationKind.SECRET_REALM, "秘境",
                parent_location_id="cangwu", hidden=True, concealment=1.0, discovered=True,
            ),
        })
        world = WorldView(_state=state)
        result = scan_for_hidden_locations("cangwu", world, _FixedRng(0.0))

        self.assertIsNone(result.found_location_id)

    def test_no_hidden_candidates_at_location_is_a_plain_miss(self):
        world = _world_with_hidden(concealment=0.9)
        result = scan_for_hidden_locations("somewhere_else", world, _FixedRng(0.0))

        self.assertIsNone(result.found_location_id)


if __name__ == "__main__":
    unittest.main()
