import unittest

from starlette.testclient import TestClient

from bootstrap import build_app
from content.seed import seed_all
from controller.admin_controller import register_admin_routes
from fastapi import FastAPI


def _make_client() -> TestClient:
    """跟 web_controller.create_app() 接线一样，但跳过 chat 路由，只挂 admin
    路由——admin 功能应该能独立于聊天前端工作。"""
    app_ctx = build_app()
    seed_all(app_ctx)
    fastapi_app = FastAPI()
    register_admin_routes(fastapi_app, app_ctx)
    return TestClient(fastapi_app)


class AdminLocationTests(unittest.TestCase):
    def test_list_locations_returns_seeded_content(self):
        client = _make_client()
        resp = client.get("/api/admin/locations")
        self.assertEqual(resp.status_code, 200)
        ids = {loc["location_id"] for loc in resp.json()}
        self.assertIn("cangwu", ids)  # content/map.py 里的苍梧城

    def test_save_and_delete_location_round_trips(self):
        client = _make_client()
        resp = client.post(
            "/api/admin/locations",
            json={"location_id": "t1", "name": "测试地", "kind": "城市", "location_type": "城市"},
        )
        self.assertTrue(resp.json()["ok"])
        ids = {loc["location_id"] for loc in client.get("/api/admin/locations").json()}
        self.assertIn("t1", ids)

        resp = client.delete("/api/admin/locations/t1")
        self.assertTrue(resp.json()["ok"])
        resp = client.delete("/api/admin/locations/t1")
        self.assertEqual(resp.status_code, 404)

    def test_save_location_rejects_unknown_kind(self):
        client = _make_client()
        resp = client.post(
            "/api/admin/locations",
            json={"location_id": "t2", "name": "x", "kind": "不存在的类型", "location_type": "x"},
        )
        body = resp.json()
        self.assertFalse(body["ok"])
        self.assertTrue(body["field_errors"])

    def test_deleting_location_also_removes_its_routes(self):
        client = _make_client()
        client.post("/api/admin/locations", json={"location_id": "a", "name": "A", "kind": "城市", "location_type": "城市"})
        client.post("/api/admin/locations", json={"location_id": "b", "name": "B", "kind": "城市", "location_type": "城市"})
        client.post("/api/admin/routes", json={"from_id": "a", "to_id": "b"})
        client.delete("/api/admin/locations/a")
        remaining = client.get("/api/admin/routes").json()
        self.assertFalse(any(r["from_id"] == "a" or r["to_id"] == "a" for r in remaining))


class AdminItemTests(unittest.TestCase):
    def test_save_list_delete_item(self):
        client = _make_client()
        resp = client.post(
            "/api/admin/items",
            json={"item_id": "widget", "kind": "material", "name": "小玩意", "description": "无"},
        )
        self.assertTrue(resp.json()["ok"])
        ids = {i["item_id"] for i in client.get("/api/admin/items").json()}
        self.assertIn("widget", ids)
        resp = client.delete("/api/admin/items/widget")
        self.assertTrue(resp.json()["ok"])


class AdminEventTests(unittest.TestCase):
    def _base_event(self, **overrides) -> dict:
        base = {
            "event_id": "admin_test_event",
            "applicable_locations": ["*"],
            "predicate": None,
            "weight": 1.0,
            "duration_shichen": 1,
            "cooldown_shichen": 0,
            "tags": ["测试"],
            "aliases": [],
            "result_pool": [],
            "variants": [{"text": "测试文案。", "weight": 1.0}],
            "is_draft": True,
            "is_command": False,
        }
        base.update(overrides)
        return base

    def test_save_then_fetch_round_trips(self):
        client = _make_client()
        resp = client.post("/api/admin/events", json=self._base_event())
        self.assertTrue(resp.json()["ok"])
        detail = client.get("/api/admin/events/admin_test_event").json()
        self.assertEqual(detail["variants"][0]["text"], "测试文案。")
        self.assertTrue(detail["is_draft"])

    def test_bad_predicate_arity_rejected_with_field_error(self):
        client = _make_client()
        bad = self._base_event(predicate={"op": "AND", "items": [{"type": "money_gte", "args": [1, 2]}]})
        resp = client.post("/api/admin/events", json=bad)
        body = resp.json()
        self.assertFalse(body["ok"])
        self.assertIn("money_gte", body["field_errors"][0]["message"])

    def test_dangling_item_reference_rejected(self):
        client = _make_client()
        bad = self._base_event(result_pool=[{"kind": "item_drop", "item_id": "does_not_exist", "n": 1}])
        resp = client.post("/api/admin/events", json=bad)
        self.assertFalse(resp.json()["ok"])

    def test_item_reference_accepted_once_item_exists(self):
        client = _make_client()
        client.post("/api/admin/items", json={"item_id": "widget", "kind": "material", "name": "小玩意"})
        ok = self._base_event(result_pool=[{"kind": "item_drop", "item_id": "widget", "n": 1}])
        resp = client.post("/api/admin/events", json=ok)
        self.assertTrue(resp.json()["ok"])

    def test_publish_then_unpublish_round_trip(self):
        client = _make_client()
        client.post("/api/admin/events", json=self._base_event())
        resp = client.post("/api/admin/events/admin_test_event/publish")
        self.assertTrue(resp.json()["ok"])
        self.assertFalse(client.get("/api/admin/events/admin_test_event").json()["is_draft"])

        resp = client.post("/api/admin/events/admin_test_event/unpublish")
        self.assertTrue(resp.json()["ok"])
        self.assertTrue(client.get("/api/admin/events/admin_test_event").json()["is_draft"])

    def test_delete_event(self):
        client = _make_client()
        client.post("/api/admin/events", json=self._base_event())
        resp = client.delete("/api/admin/events/admin_test_event")
        self.assertTrue(resp.json()["ok"])
        self.assertEqual(client.get("/api/admin/events/admin_test_event").status_code, 404)

    def test_event_list_includes_drafts_unlike_gameplay_pool(self):
        """管理列表必须能看到草稿——README 1.3.3："草稿不进入合格池"说的是对局，
        不是编辑器看不见自己刚存的草稿。"""
        client = _make_client()
        client.post("/api/admin/events", json=self._base_event())
        summaries = client.get("/api/admin/events").json()
        ids = {e["event_id"] for e in summaries}
        self.assertIn("admin_test_event", ids)
        draft_entry = next(e for e in summaries if e["event_id"] == "admin_test_event")
        self.assertTrue(draft_entry["is_draft"])


class AdminSimulateTests(unittest.TestCase):
    def test_simulate_reports_pass_and_distribution(self):
        client = _make_client()
        client.post(
            "/api/admin/events",
            json={
                "event_id": "sim_test_event",
                "applicable_locations": ["酒楼"],
                "predicate": None,
                "weight": 5.0,
                "duration_shichen": 0,
                "cooldown_shichen": 0,
                "tags": ["测试"],
                "aliases": [],
                "result_pool": [],
                "variants": [{"text": "测试。", "weight": 1.0}],
                "is_draft": False,
                "is_command": False,
            },
        )
        resp = client.post(
            "/api/admin/simulate",
            json={"event_id": "sim_test_event", "context_snapshot": {"地点类型": "酒楼"}, "sample_n": 30},
        )
        body = resp.json()
        self.assertTrue(body["passed_coarse_filter"])
        self.assertGreater(sum(body["hit_distribution"].values()), 0)


if __name__ == "__main__":
    unittest.main()
