import unittest

from starlette.testclient import TestClient

from bootstrap import build_app
from content.seed import seed_all
from controller.admin_controller import register_admin_routes
from fastapi import FastAPI


def _make_client(
    llm_location_author=None, llm_item_author=None, llm_event_flavor_author=None,
    embedding=None, llm_result_text_parser=None,
) -> TestClient:
    """跟 web_controller.create_app() 接线一样，但跳过 chat 路由，只挂 admin
    路由——admin 功能应该能独立于聊天前端工作。"""
    app_ctx = build_app()
    seed_all(app_ctx)
    fastapi_app = FastAPI()
    register_admin_routes(
        fastapi_app, app_ctx, llm_location_author, llm_item_author, llm_event_flavor_author,
        embedding, llm_result_text_parser,
    )
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

    def test_empty_variants_no_longer_rejected(self):
        """variants 可以留空——事件命中时若为空，PlayTurnService._ensure_variants
        会现场调 LlmEventWriter 补一句并存回，不再要求编辑器表单里必须先填一条。"""
        client = _make_client()
        resp = client.post("/api/admin/events", json=self._base_event(variants=[]))
        self.assertTrue(resp.json()["ok"])
        detail = client.get("/api/admin/events/admin_test_event").json()
        self.assertEqual(detail["variants"], [])

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


class _FakeEmbeddingPort:
    def __init__(self, vector=None, error: Exception | None = None) -> None:
        self._vector = vector if vector is not None else [1.0, 0.0]
        self._error = error
        self.last_text = None

    def embed(self, text):
        self.last_text = text
        if self._error is not None:
            raise self._error
        return self._vector


class _FakeResultTextParser:
    def __init__(self, result_pool=None, item_query="", error: Exception | None = None) -> None:
        self._result_pool = result_pool if result_pool is not None else []
        self._item_query = item_query
        self._error = error
        self.last_text = None

    def parse(self, result_text):
        from model.repositories.llm.llm_result_text_parser import ParsedResult

        self.last_text = result_text
        if self._error is not None:
            raise self._error
        return ParsedResult(state_changes=self._result_pool, item_query=self._item_query)


class AdminEventPredicateTextAndResultTextTests(unittest.TestCase):
    """事件页"谓词/结果池 JSON"换成"触发条件/结果"文字描述后的保存路径：
    predicate_text -> predicate_embedding（EmbeddingPort），result_text ->
    result_pool（LlmResultTextParser）。"""

    def _base_event(self, **overrides) -> dict:
        base = {
            "event_id": "predtext_test_event",
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
            "predicate_text": "",
            "result_text": "",
        }
        base.update(overrides)
        return base

    def test_predicate_text_gets_embedded_and_stored(self):
        embedding = _FakeEmbeddingPort(vector=[0.1, 0.2, 0.3])
        client = _make_client(embedding=embedding)
        resp = client.post("/api/admin/events", json=self._base_event(predicate_text="玩家境界至少到金丹期"))
        self.assertTrue(resp.json()["ok"])
        self.assertEqual(embedding.last_text, "玩家境界至少到金丹期")
        detail = client.get("/api/admin/events/predtext_test_event").json()
        self.assertEqual(detail["predicate_text"], "玩家境界至少到金丹期")
        self.assertEqual(detail["predicate_embedding"], [0.1, 0.2, 0.3])

    def test_blank_predicate_text_stores_empty_embedding(self):
        embedding = _FakeEmbeddingPort()
        client = _make_client(embedding=embedding)
        client.post("/api/admin/events", json=self._base_event(predicate_text=""))
        self.assertIsNone(embedding.last_text)  # 空文本不该去调向量服务
        detail = client.get("/api/admin/events/predtext_test_event").json()
        self.assertEqual(detail["predicate_embedding"], [])

    def test_no_embedding_port_configured_still_saves_successfully(self):
        """没配置向量服务时保存这个动作本身不能失败——退化成空向量。"""
        client = _make_client(embedding=None)
        resp = client.post("/api/admin/events", json=self._base_event(predicate_text="随便什么条件"))
        self.assertTrue(resp.json()["ok"])
        detail = client.get("/api/admin/events/predtext_test_event").json()
        self.assertEqual(detail["predicate_embedding"], [])

    def test_embedding_failure_does_not_fail_save(self):
        embedding = _FakeEmbeddingPort(error=RuntimeError("网络超时"))
        client = _make_client(embedding=embedding)
        resp = client.post("/api/admin/events", json=self._base_event(predicate_text="随便什么条件"))
        self.assertTrue(resp.json()["ok"])
        detail = client.get("/api/admin/events/predtext_test_event").json()
        self.assertEqual(detail["predicate_embedding"], [])

    def test_result_text_gets_parsed_into_result_pool(self):
        parser = _FakeResultTextParser(result_pool=[{"kind": "state_change", "field": "money", "delta": -5.0}])
        client = _make_client(llm_result_text_parser=parser)
        resp = client.post("/api/admin/events", json=self._base_event(result_text="花费五两银子买下了金龙鱼"))
        self.assertTrue(resp.json()["ok"])
        self.assertEqual(parser.last_text, "花费五两银子买下了金龙鱼")
        detail = client.get("/api/admin/events/predtext_test_event").json()
        self.assertEqual(detail["result_text"], "花费五两银子买下了金龙鱼")
        self.assertEqual(detail["result_pool"], [{"kind": "state_change", "field": "money", "delta": -5.0, "set_to": None}])

    def test_item_query_resolves_to_real_item_via_embedding_match(self):
        """结果描述提到"获得一把长剑"——不让 LLM 自己编 item_id，而是拿这句话的
        向量去物品库里找语义最接近的真实物品（同一个 embedding 端口，物品保存时
        和 item_query 解析时都返回同一个向量，相似度=1，必然命中）。"""
        embedding = _FakeEmbeddingPort(vector=[1.0, 0.0, 0.0])
        parser = _FakeResultTextParser(item_query="一把锋利的长剑")
        client = _make_client(embedding=embedding, llm_result_text_parser=parser)
        client.post("/api/admin/items", json={
            "item_id": "sharp_sword", "kind": "gear", "name": "青锋剑", "description": "一把锋利的长剑",
        })
        resp = client.post("/api/admin/events", json=self._base_event(result_text="你从遗迹里捡到了一把锋利的长剑"))
        self.assertTrue(resp.json()["ok"])
        detail = client.get("/api/admin/events/predtext_test_event").json()
        self.assertIn({"kind": "item_drop", "item_id": "sharp_sword", "n": 1}, detail["result_pool"])

    def test_item_query_resolves_via_local_fallback_when_no_embedding_configured(self):
        """没配置 EmbeddingPort（或 LLM 向量化失败）时，item_query 解析退到本地
        词袋向量（model/services/local_embedding.py），不再直接放弃匹配——物品
        的 name+description 和 item_query 共享大量字/词，本地相似度足够高。"""
        parser = _FakeResultTextParser(item_query="一把锋利的长剑")
        client = _make_client(embedding=None, llm_result_text_parser=parser)
        client.post("/api/admin/items", json={
            "item_id": "sharp_sword", "kind": "gear", "name": "青锋剑", "description": "一把锋利的长剑",
        })
        resp = client.post("/api/admin/events", json=self._base_event(result_text="你从遗迹里捡到了一把锋利的长剑"))
        self.assertTrue(resp.json()["ok"])
        detail = client.get("/api/admin/events/predtext_test_event").json()
        self.assertIn({"kind": "item_drop", "item_id": "sharp_sword", "n": 1}, detail["result_pool"])

    def test_item_query_resolves_via_local_fallback_when_embedding_call_fails(self):
        """EmbeddingPort 配置了，但调用失败（网络问题、账户余额不足等）——同样
        退到本地向量，而不是像旧行为那样直接放弃这次物品匹配。"""
        embedding = _FakeEmbeddingPort(error=RuntimeError("账户余额不足"))
        parser = _FakeResultTextParser(item_query="一把锋利的长剑")
        client = _make_client(embedding=embedding, llm_result_text_parser=parser)
        client.post("/api/admin/items", json={
            "item_id": "sharp_sword", "kind": "gear", "name": "青锋剑", "description": "一把锋利的长剑",
        })
        resp = client.post("/api/admin/events", json=self._base_event(result_text="你从遗迹里捡到了一把锋利的长剑"))
        self.assertTrue(resp.json()["ok"])
        detail = client.get("/api/admin/events/predtext_test_event").json()
        self.assertIn({"kind": "item_drop", "item_id": "sharp_sword", "n": 1}, detail["result_pool"])

    def test_no_matching_item_leaves_result_pool_empty(self):
        """物品库里没有语义接近的东西——宁可不发物品，也不乱发一个不相关的。"""
        class _OrthogonalOnQuery:
            def embed(self, text):
                # 物品（丹药，不含"剑"字）和 item_query（长剑，含"剑"字）编码成正交
                # 向量，模拟"语义完全不沾边"。
                return [0.0, 1.0] if "剑" in text else [1.0, 0.0]

        parser = _FakeResultTextParser(item_query="一把锋利的长剑")
        client = _make_client(embedding=_OrthogonalOnQuery(), llm_result_text_parser=parser)
        client.post("/api/admin/items", json={
            "item_id": "warm_pill", "kind": "pill", "name": "培元丹", "description": "一颗温补的丹药",
        })
        resp = client.post("/api/admin/events", json=self._base_event(result_text="你从遗迹里捡到了一把锋利的长剑"))
        self.assertTrue(resp.json()["ok"])
        detail = client.get("/api/admin/events/predtext_test_event").json()
        self.assertEqual(detail["result_pool"], [])

    def test_blank_result_text_preserves_submitted_result_pool(self):
        """result_text 留空时不解析——前端会把加载时的旧 result_pool 原样传回来，
        后端不该去动它。"""
        parser = _FakeResultTextParser()
        client = _make_client(llm_result_text_parser=parser)
        resp = client.post("/api/admin/events", json=self._base_event(
            result_text="", result_pool=[{"kind": "state_change", "field": "money", "delta": 3}],
        ))
        self.assertTrue(resp.json()["ok"])
        self.assertIsNone(parser.last_text)
        detail = client.get("/api/admin/events/predtext_test_event").json()
        self.assertEqual(detail["result_pool"], [{"kind": "state_change", "field": "money", "delta": 3.0, "set_to": None}])

    def test_no_parser_configured_still_saves_with_text_only(self):
        client = _make_client(llm_result_text_parser=None)
        resp = client.post("/api/admin/events", json=self._base_event(result_text="花了点钱"))
        self.assertTrue(resp.json()["ok"])
        detail = client.get("/api/admin/events/predtext_test_event").json()
        self.assertEqual(detail["result_text"], "花了点钱")
        self.assertEqual(detail["result_pool"], [])

    def test_parser_failure_does_not_fail_save(self):
        parser = _FakeResultTextParser(error=RuntimeError("解析失败"))
        client = _make_client(llm_result_text_parser=parser)
        resp = client.post("/api/admin/events", json=self._base_event(result_text="花了点钱"))
        self.assertTrue(resp.json()["ok"])


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


class _FakeLocationAuthor:
    def __init__(self, items=None, error: Exception | None = None) -> None:
        self._items = items if items is not None else [{"name": "苍梧城", "kind": "城市"}]
        self._error = error

    def generate_locations(self, kinds, count):
        if self._error is not None:
            raise self._error
        return self._items


class AdminGenerateLocationsTests(unittest.TestCase):
    def test_no_author_configured_returns_ok_false(self):
        client = _make_client(llm_location_author=None)
        resp = client.post("/api/admin/generate_locations", json={"kinds": ["城市"], "count": 3})
        body = resp.json()
        self.assertFalse(body["ok"])
        self.assertIn("LLM", body["error"])
        self.assertEqual(body["items"], [])

    def test_configured_author_returns_items(self):
        client = _make_client(llm_location_author=_FakeLocationAuthor(
            items=[{"name": "苍梧城", "kind": "城市"}, {"name": "黑风谷", "kind": "荒野"}]
        ))
        resp = client.post("/api/admin/generate_locations", json={"kinds": ["城市", "荒野"], "count": 2})
        body = resp.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["items"], [{"name": "苍梧城", "kind": "城市"}, {"name": "黑风谷", "kind": "荒野"}])

    def test_author_exception_returns_ok_false_not_500(self):
        client = _make_client(llm_location_author=_FakeLocationAuthor(error=RuntimeError("网络超时")))
        resp = client.post("/api/admin/generate_locations", json={"kinds": ["城市"], "count": 1})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertFalse(body["ok"])
        self.assertIn("网络超时", body["error"])


class _FakeItemAuthor:
    def __init__(self, items=None, error: Exception | None = None) -> None:
        self._items = items if items is not None else [{"name": "培元丹", "kind": "pill", "description": "常见丹药"}]
        self._error = error

    def generate_items(self, kinds, count, novel=""):
        if self._error is not None:
            raise self._error
        return self._items


class AdminGenerateItemsTests(unittest.TestCase):
    def test_no_author_configured_returns_ok_false(self):
        client = _make_client(llm_item_author=None)
        resp = client.post("/api/admin/generate_items", json={"kinds": ["pill"], "count": 3})
        body = resp.json()
        self.assertFalse(body["ok"])
        self.assertIn("LLM", body["error"])
        self.assertEqual(body["items"], [])

    def test_configured_author_returns_items(self):
        client = _make_client(llm_item_author=_FakeItemAuthor(
            items=[{"name": "培元丹", "kind": "pill", "description": "疗伤"}, {"name": "赤血材", "kind": "material", "description": "炼器"}]
        ))
        resp = client.post("/api/admin/generate_items", json={"kinds": ["pill", "material"], "count": 2})
        body = resp.json()
        self.assertTrue(body["ok"])
        self.assertEqual(len(body["items"]), 2)

    def test_blank_kinds_is_accepted_not_rejected(self):
        """类型留空 = 不限定，不是缺必填字段——不该被 schema 或 endpoint 拦下来。"""
        client = _make_client(llm_item_author=_FakeItemAuthor())
        resp = client.post("/api/admin/generate_items", json={"kinds": [], "count": 1})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])

    def test_omitted_kinds_defaults_to_blank(self):
        client = _make_client(llm_item_author=_FakeItemAuthor())
        resp = client.post("/api/admin/generate_items", json={"count": 1})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])

    def test_author_exception_returns_ok_false_not_500(self):
        client = _make_client(llm_item_author=_FakeItemAuthor(error=RuntimeError("超时")))
        resp = client.post("/api/admin/generate_items", json={"kinds": ["gear"], "count": 1})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertFalse(body["ok"])
        self.assertIn("超时", body["error"])


class _FakeEventFlavorAuthor:
    def __init__(self, flavors=None, error: Exception | None = None) -> None:
        self._flavors = flavors if flavors is not None else [
            {"tags": ["奇遇"], "aliases": [], "variants": ["你在{地点}钓上了一条通体金红的鱼。"]}
        ]
        self._error = error

    def generate_event_flavors(self, description, count):
        if self._error is not None:
            raise self._error
        return self._flavors


class AdminGenerateEventsTests(unittest.TestCase):
    def test_item_query_from_ai_flavor_resolves_to_real_item(self):
        """AI 批量生成事件时给的 item_query 也走同一条向量匹配路径，不是只有
        手工编辑"结果"文字描述才有这个能力。"""
        embedding = _FakeEmbeddingPort(vector=[1.0, 0.0])
        flavor_author = _FakeEventFlavorAuthor(flavors=[{
            "tags": ["奇遇"], "aliases": [], "variants": ["你捡到了一把剑。"], "item_query": "一把剑",
        }])
        client = _make_client(llm_event_flavor_author=flavor_author, embedding=embedding)
        client.post("/api/admin/items", json={
            "item_id": "found_sword", "kind": "gear", "name": "无名剑", "description": "剑",
        })
        resp = client.post("/api/admin/generate_events", json={"description": "捡剑", "count": 1})
        body = resp.json()
        self.assertTrue(body["ok"])
        detail = client.get(f"/api/admin/events/{body['event_ids'][0]}").json()
        self.assertIn({"kind": "item_drop", "item_id": "found_sword", "n": 1}, detail["result_pool"])

    def test_no_author_configured_returns_ok_false(self):
        client = _make_client(llm_event_flavor_author=None)
        resp = client.post("/api/admin/generate_events", json={"description": "酒楼钓鱼", "count": 1})
        body = resp.json()
        self.assertFalse(body["ok"])
        self.assertIn("LLM", body["error"])

    def test_blank_description_is_accepted_not_rejected(self):
        """情节描述留空是"让 AI 自己构思"，不是缺必填字段——不该被 schema 或
        endpoint 拦下来。"""
        client = _make_client(llm_event_flavor_author=_FakeEventFlavorAuthor())
        resp = client.post("/api/admin/generate_events", json={"description": "", "count": 1})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])

    def test_omitted_description_defaults_to_blank(self):
        client = _make_client(llm_event_flavor_author=_FakeEventFlavorAuthor())
        resp = client.post("/api/admin/generate_events", json={"count": 1})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])

    def test_configured_author_creates_draft_events(self):
        client = _make_client(llm_event_flavor_author=_FakeEventFlavorAuthor())
        resp = client.post("/api/admin/generate_events", json={
            "description": "酒楼里有人钓到金龙鱼，围观后可买", "applicable_locations": ["酒楼"], "count": 1,
        })
        body = resp.json()
        self.assertTrue(body["ok"])
        self.assertEqual(len(body["event_ids"]), 1)
        # 生成的事件要能在编辑器里查到、且是草稿态，不直接进合格池
        detail = client.get(f"/api/admin/events/{body['event_ids'][0]}").json()
        self.assertTrue(detail["is_draft"])
        self.assertEqual(detail["applicable_locations"], ["酒楼"])
        self.assertIn("钓上了", detail["variants"][0]["text"])

    def test_full_flavor_data_flows_through_to_saved_event(self):
        """AI 生成的事件数据要跟人工填的一样完整——weight/duration_shichen/
        cooldown_shichen/priority/result_pool 都该是 LlmEventFlavorAuthor 给出的
        值，不是写死的默认值。"""
        client = _make_client(llm_event_flavor_author=_FakeEventFlavorAuthor(flavors=[{
            "tags": ["经济"], "aliases": ["卖鱼"], "variants": ["你把鱼卖给了老板。"],
            "weight": 2.0, "duration_shichen": 2, "cooldown_shichen": 12, "priority": 6,
            "result_pool": [{"kind": "state_change", "field": "money", "delta": 15.0}],
        }]))
        resp = client.post("/api/admin/generate_events", json={"description": "卖鱼给钱", "count": 1})
        body = resp.json()
        self.assertTrue(body["ok"])
        detail = client.get(f"/api/admin/events/{body['event_ids'][0]}").json()
        self.assertEqual(detail["weight"], 2.0)
        self.assertEqual(detail["duration_shichen"], 2)
        self.assertEqual(detail["cooldown_shichen"], 12)
        self.assertEqual(detail["priority"], 6)
        self.assertEqual(detail["result_pool"], [{"kind": "state_change", "field": "money", "delta": 15.0, "set_to": None}])
        self.assertTrue(detail["is_command"])  # 给了 aliases，应该按命令型事件处理

    def test_invalid_placeholder_in_variant_is_rejected_but_reported(self):
        """占位符不在白名单里（README/event_validation.py 的占位符白名单）该被拒，
        走 field_errors，而不是让非法文案混进事件库。"""
        client = _make_client(llm_event_flavor_author=_FakeEventFlavorAuthor(
            flavors=[{"tags": [], "aliases": [], "variants": ["你获得了{未知占位符}"]}]
        ))
        resp = client.post("/api/admin/generate_events", json={"description": "随便", "count": 1})
        body = resp.json()
        self.assertFalse(body["ok"])
        self.assertEqual(body["event_ids"], [])
        self.assertTrue(body["field_errors"])

    def test_author_exception_returns_ok_false_not_500(self):
        client = _make_client(llm_event_flavor_author=_FakeEventFlavorAuthor(error=RuntimeError("超时")))
        resp = client.post("/api/admin/generate_events", json={"description": "随便", "count": 1})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertFalse(body["ok"])
        self.assertIn("超时", body["error"])

    def test_empty_flavor_list_returns_ok_false_with_helpful_error(self):
        client = _make_client(llm_event_flavor_author=_FakeEventFlavorAuthor(flavors=[]))
        resp = client.post("/api/admin/generate_events", json={"description": "随便", "count": 1})
        body = resp.json()
        self.assertFalse(body["ok"])
        self.assertIsNotNone(body["error"])


if __name__ == "__main__":
    unittest.main()
