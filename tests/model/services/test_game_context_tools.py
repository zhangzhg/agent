import unittest

from model.domain.map import Location, LocationKind, Route, WorldState, WorldView
from model.services.game_context_tools import (
    build_tool_impls,
    build_tool_specs,
    get_current_location,
    get_player_status,
    list_all_locations,
    list_reachable_locations,
)
from tests.helpers import make_agent


def _world_with_routes() -> WorldView:
    state = WorldState(
        locations={
            "cangwu": Location("cangwu", "苍梧城", LocationKind.CITY, "城市"),
            "luoyan": Location("luoyan", "落雁镇", LocationKind.CITY, "城市"),
            "guixu": Location(
                "guixu", "归墟秘境", LocationKind.SECRET_REALM, "秘境",
                parent_location_id="cangwu", hidden=True, discovered=False,
            ),
        },
        routes=[Route("cangwu", "luoyan", move_cost_shichen=3)],
    )
    return WorldView(_state=state)


class GetPlayerStatusTests(unittest.TestCase):
    def test_reports_location_and_core_attributes(self):
        agent = make_agent(location_id="cangwu", money=8, realm="炼气期")
        world = _world_with_routes()

        status = get_player_status(agent, world)

        self.assertEqual(status["location_id"], "cangwu")
        self.assertEqual(status["location_name"], "苍梧城")
        self.assertEqual(status["realm"], "炼气期")
        self.assertEqual(status["money"], 8)
        self.assertIn("game_time", status)

    def test_flags_are_sorted_list_not_set(self):
        agent = make_agent(flags={"有门派归属", "已破戒"})
        world = _world_with_routes()

        status = get_player_status(agent, world)

        self.assertEqual(status["flags"], sorted({"有门派归属", "已破戒"}))


class GetCurrentLocationTests(unittest.TestCase):
    def test_reports_name_type_weather(self):
        agent = make_agent(location_id="cangwu", location_type="城市")
        world = _world_with_routes()

        info = get_current_location(agent, world)

        self.assertEqual(info["name"], "苍梧城")
        self.assertEqual(info["location_type"], "城市")
        self.assertIn("weather", info)


class ListAllLocationsTests(unittest.TestCase):
    def test_hidden_undiscovered_location_excluded(self):
        world = _world_with_routes()

        names = [loc["name"] for loc in list_all_locations(world)]

        self.assertIn("苍梧城", names)
        self.assertIn("落雁镇", names)
        self.assertNotIn("归墟秘境", names)

    def test_discovered_hidden_location_is_included(self):
        world = _world_with_routes()
        world.mutable_state().get("guixu").discovered = True

        names = [loc["name"] for loc in list_all_locations(world)]

        self.assertIn("归墟秘境", names)


class ListReachableLocationsTests(unittest.TestCase):
    def test_returns_neighbor_with_cost(self):
        world = _world_with_routes()
        agent = make_agent(location_id="cangwu")

        reachable = list_reachable_locations(agent, world)

        self.assertEqual(len(reachable), 1)
        self.assertEqual(reachable[0]["name"], "落雁镇")
        self.assertEqual(reachable[0]["move_cost_shichen"], 3)

    def test_no_routes_returns_empty(self):
        world = _world_with_routes()
        agent = make_agent(location_id="guixu")  # 没有任何 Route 以它为端点

        self.assertEqual(list_reachable_locations(agent, world), [])

    def test_bidirectional_route_reachable_from_either_end(self):
        """Route 默认双向——反向那一端也该能通过 WorldState.neighbors 查到，
        不该因为 Route 只记了一个方向就漏报。"""
        world = _world_with_routes()
        agent = make_agent(location_id="luoyan")
        # luoyan -> cangwu 是反向，neighbors() 里 bidirectional=True 应该补上
        state = world.mutable_state()
        state.locations["luoyan"] = Location("luoyan", "落雁镇", LocationKind.CITY, "城市")

        reachable = list_reachable_locations(agent, world)

        self.assertEqual([loc["name"] for loc in reachable], ["苍梧城"])


class ToolSpecsAndImplsTests(unittest.TestCase):
    def test_four_tools_defined_with_no_required_params(self):
        specs = build_tool_specs()
        names = {spec["function"]["name"] for spec in specs}

        self.assertEqual(
            names,
            {"get_player_status", "get_current_location", "list_all_locations", "list_reachable_locations"},
        )
        for spec in specs:
            self.assertEqual(spec["function"]["parameters"]["properties"], {})

    def test_impls_are_zero_arg_callables_bound_to_agent_and_world(self):
        agent = make_agent(location_id="cangwu")
        world = _world_with_routes()
        impls = build_tool_impls(agent, world)

        self.assertEqual(impls["get_player_status"]()["location_id"], "cangwu")
        self.assertEqual(len(impls["list_reachable_locations"]()), 1)


if __name__ == "__main__":
    unittest.main()
