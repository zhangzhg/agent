import unittest

from model.repositories.llm.llm_event_flavor_author import LlmEventFlavorAuthor
from model.services.result_pool_safety import SAFE_STATE_CHANGE_FIELDS


class FakeLlmClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.last_prompt = None

    def complete(self, prompt: str) -> str:
        self.last_prompt = prompt
        return self.response


class LlmEventFlavorAuthorTests(unittest.TestCase):
    def test_parses_full_shape_with_defaults_when_fields_missing(self):
        client = FakeLlmClient(
            '[{"tags": ["奇遇"], "aliases": [], "variants": ["你在{地点}钓上了一条通体金红的鱼。"]}]'
        )
        author = LlmEventFlavorAuthor(client)
        flavors = author.generate_event_flavors("酒楼里有人钓到金龙鱼", 1)
        self.assertEqual(flavors, [{
            "tags": ["奇遇"], "aliases": [], "variants": ["你在{地点}钓上了一条通体金红的鱼。"],
            "weight": 1.0, "duration_shichen": 1, "cooldown_shichen": 0, "priority": 5,
            "result_pool": [], "item_query": "",
        }])

    def test_full_data_passes_through(self):
        client = FakeLlmClient(
            '[{"tags": ["经济"], "aliases": ["卖鱼"], "variants": ["文案"], '
            '"weight": 2.0, "duration_shichen": 2, "cooldown_shichen": 12, "priority": 6, '
            '"result_pool": [{"kind": "state_change", "field": "money", "delta": 15}]}]'
        )
        author = LlmEventFlavorAuthor(client)
        flavors = author.generate_event_flavors("卖鱼给钱", 1)
        self.assertEqual(flavors[0]["weight"], 2.0)
        self.assertEqual(flavors[0]["duration_shichen"], 2)
        self.assertEqual(flavors[0]["cooldown_shichen"], 12)
        self.assertEqual(flavors[0]["priority"], 6)
        self.assertEqual(flavors[0]["result_pool"], [{"kind": "state_change", "field": "money", "delta": 15.0}])

    def test_out_of_range_numeric_fields_are_clamped(self):
        client = FakeLlmClient(
            '[{"tags": [], "aliases": [], "variants": ["文案"], '
            '"weight": 999, "duration_shichen": -5, "cooldown_shichen": 9999, "priority": 0}]'
        )
        author = LlmEventFlavorAuthor(client)
        flavor = author.generate_event_flavors("情节", 1)[0]
        self.assertLessEqual(flavor["weight"], 5.0)
        self.assertGreaterEqual(flavor["duration_shichen"], 0)
        self.assertLessEqual(flavor["cooldown_shichen"], 48)
        self.assertGreaterEqual(flavor["priority"], 1)

    def test_non_numeric_fields_fall_back_to_defaults(self):
        client = FakeLlmClient('[{"tags": [], "aliases": [], "variants": ["文案"], "weight": "很多"}]')
        author = LlmEventFlavorAuthor(client)
        flavor = author.generate_event_flavors("情节", 1)[0]
        self.assertEqual(flavor["weight"], 1.0)

    def test_result_pool_drops_unsafe_field_names(self):
        client = FakeLlmClient(
            '[{"tags": [], "aliases": [], "variants": ["文案"], "result_pool": ['
            '{"kind": "state_change", "field": "money", "delta": 5}, '
            '{"kind": "state_change", "field": "灵气", "delta": 999}]}]'
        )
        author = LlmEventFlavorAuthor(client)
        flavor = author.generate_event_flavors("情节", 1)[0]
        self.assertEqual(flavor["result_pool"], [{"kind": "state_change", "field": "money", "delta": 5.0}])

    def test_result_pool_drops_non_state_change_kinds(self):
        """item_drop/chain_event 这些需要引用真实存在的 item_id/event_id，模型
        编的 id 十有八九悬空——直接丢弃，不留给 validate_event_def() 去拒。"""
        client = FakeLlmClient(
            '[{"tags": [], "aliases": [], "variants": ["文案"], "result_pool": ['
            '{"kind": "item_drop", "item_id": "不存在的物品", "n": 1}]}]'
        )
        author = LlmEventFlavorAuthor(client)
        flavor = author.generate_event_flavors("情节", 1)[0]
        self.assertEqual(flavor["result_pool"], [])

    def test_result_pool_capped_at_three_entries(self):
        entries = ",".join(
            '{"kind": "state_change", "field": "money", "delta": 1}' for _ in range(6)
        )
        client = FakeLlmClient('[{"tags": [], "aliases": [], "variants": ["文案"], "result_pool": [' + entries + ']}]')
        author = LlmEventFlavorAuthor(client)
        flavor = author.generate_event_flavors("情节", 1)[0]
        self.assertEqual(len(flavor["result_pool"]), 3)

    def test_item_query_passed_through(self):
        client = FakeLlmClient(
            '[{"tags": [], "aliases": [], "variants": ["文案"], "item_query": "一把锋利的长剑"}]'
        )
        author = LlmEventFlavorAuthor(client)
        flavor = author.generate_event_flavors("情节", 1)[0]
        self.assertEqual(flavor["item_query"], "一把锋利的长剑")

    def test_missing_item_query_defaults_to_blank(self):
        client = FakeLlmClient('[{"tags": [], "aliases": [], "variants": ["文案"]}]')
        author = LlmEventFlavorAuthor(client)
        flavor = author.generate_event_flavors("情节", 1)[0]
        self.assertEqual(flavor["item_query"], "")

    def test_safe_state_change_fields_are_all_used_in_seed_content(self):
        """交叉检查：白名单里的字段名跟 content/events/*.py 里手写的 StateChange
        用的是同一套拼写，防止两边悄悄漂移。"""
        self.assertEqual(set(SAFE_STATE_CHANGE_FIELDS), {"money", "satiety", "cultivation", "heart_demon"})

    def test_strips_markdown_code_fence(self):
        client = FakeLlmClient('```json\n[{"tags": [], "aliases": [], "variants": ["文案"]}]\n```')
        author = LlmEventFlavorAuthor(client)
        flavors = author.generate_event_flavors("随便什么情节", 1)
        self.assertEqual(flavors[0]["variants"], ["文案"])

    def test_entry_with_no_variants_is_dropped(self):
        client = FakeLlmClient('[{"tags": ["奇遇"], "aliases": [], "variants": []}]')
        author = LlmEventFlavorAuthor(client)
        self.assertEqual(author.generate_event_flavors("情节", 1), [])

    def test_blank_variant_strings_filtered_out(self):
        client = FakeLlmClient('[{"tags": [], "aliases": [], "variants": ["  ", "真实文案"]}]')
        author = LlmEventFlavorAuthor(client)
        flavors = author.generate_event_flavors("情节", 1)
        self.assertEqual(flavors[0]["variants"], ["真实文案"])

    def test_non_json_output_yields_empty_list(self):
        client = FakeLlmClient("抱歉，我无法完成这个请求。")
        author = LlmEventFlavorAuthor(client)
        self.assertEqual(author.generate_event_flavors("情节", 3), [])

    def test_prompt_includes_description_and_count(self):
        client = FakeLlmClient("[]")
        author = LlmEventFlavorAuthor(client)
        author.generate_event_flavors("酒楼钓鱼的桥段", 5)
        self.assertIn("酒楼钓鱼的桥段", client.last_prompt)
        self.assertIn("5", client.last_prompt)

    def test_blank_description_asks_model_to_invent_its_own_scene(self):
        """情节描述留空不是"忘了填"，是明确要 AI 自己构思场景——prompt 里不能是
        一句空白的"情节描述：\n\n"，得换成一段真的指示。"""
        client = FakeLlmClient("[]")
        author = LlmEventFlavorAuthor(client)
        author.generate_event_flavors("", 2)
        self.assertNotIn("情节描述：\n\n", client.last_prompt)
        self.assertIn("自己构思", client.last_prompt)

    def test_whitespace_only_description_treated_as_blank(self):
        client = FakeLlmClient("[]")
        author = LlmEventFlavorAuthor(client)
        author.generate_event_flavors("   \n  ", 1)
        self.assertIn("自己构思", client.last_prompt)


if __name__ == "__main__":
    unittest.main()
