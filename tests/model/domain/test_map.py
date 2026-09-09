import unittest

from model.domain.map import Location, LocationKind, WorldState, WorldView


def _world(*locations: Location) -> WorldView:
    return WorldView(_state=WorldState(locations={loc.location_id: loc for loc in locations}))


class FindLocationByNameTests(unittest.TestCase):
    def test_exact_id_match(self):
        world = _world(Location("cangwu", "苍梧城", LocationKind.CITY, "城市"))
        self.assertEqual(world.find_location_by_name("cangwu").location_id, "cangwu")

    def test_exact_name_match(self):
        world = _world(Location("cangwu", "苍梧城", LocationKind.CITY, "城市"))
        self.assertEqual(world.find_location_by_name("苍梧城").location_id, "cangwu")

    def test_partial_name_substring_match(self):
        world = _world(Location("cangwu_street", "苍梧城·主街", LocationKind.CITY, "主街"))
        self.assertEqual(world.find_location_by_name("苍梧").location_id, "cangwu_street")

    def test_type_wrapped_in_natural_language_matches_when_unambiguous(self):
        """"去逛逛集市"这种类型名被自然语言包住的情况——全图只有一个"集市"类型
        的地点时应该照样能命中，模糊匹配不能因为加了安全阀就退化成必须打全名。"""
        world = _world(
            Location("cangwu", "苍梧城", LocationKind.CITY, "城市"),
            Location("market", "苍梧城·集市", LocationKind.MARKET, "集市", parent_location_id="cangwu"),
        )
        self.assertEqual(world.find_location_by_name("我想去逛逛集市").location_id, "market")

    def test_ambiguous_type_across_multiple_locations_does_not_silently_pick_one(self):
        """回归测试：两座城市都是"城市"类型，"我想去其他城市"曾经因为
        `loc.location_type in hint` 的宽松子串匹配被误判命中第一座城市——"其他"
        这个明确的排除意图被悄悄吞掉，静默传送到了错误的地方。现在应该判定为
        "找不到"（返回 None），交给上层的实时地点创作兜底，而不是瞎猜一个。"""
        world = _world(
            Location("cangwu", "苍梧城", LocationKind.CITY, "城市"),
            Location("luoyan", "落雁镇", LocationKind.CITY, "城市"),
        )
        self.assertIsNone(world.find_location_by_name("我想去其他城市"))

    def test_hidden_undiscovered_location_is_excluded(self):
        world = _world(Location("secret", "归墟秘境", LocationKind.SECRET_REALM, "秘境", hidden=True, discovered=False))
        self.assertIsNone(world.find_location_by_name("归墟秘境"))

    def test_no_match_returns_none(self):
        world = _world(Location("cangwu", "苍梧城", LocationKind.CITY, "城市"))
        self.assertIsNone(world.find_location_by_name("完全不相关的地方"))


if __name__ == "__main__":
    unittest.main()
