import unittest

from model.repositories.llm.llm_item_author import ALL_ITEM_KINDS, LlmItemAuthor


class FakeLlmClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.last_prompt = None

    def complete(self, prompt: str) -> str:
        self.last_prompt = prompt
        return self.response


class LlmItemAuthorTests(unittest.TestCase):
    def test_parses_valid_json_array(self):
        client = FakeLlmClient(
            '[{"name": "培元丹", "kind": "pill", "description": "初期修士常用的疗伤丹药"}]'
        )
        author = LlmItemAuthor(client)
        items = author.generate_items(["pill"], 1)
        self.assertEqual(items, [{"name": "培元丹", "kind": "pill", "description": "初期修士常用的疗伤丹药"}])

    def test_strips_markdown_code_fence(self):
        client = FakeLlmClient('```json\n[{"name": "赤血材", "kind": "material", "description": "炼器常用"}]\n```')
        author = LlmItemAuthor(client)
        items = author.generate_items(["material"], 1)
        self.assertEqual(items[0]["name"], "赤血材")

    def test_filters_kind_outside_whitelist(self):
        client = FakeLlmClient(
            '[{"name": "灵米", "kind": "food", "description": "煮粥用"}, '
            '{"name": "怪物", "kind": "monster", "description": "不该出现"}]'
        )
        author = LlmItemAuthor(client)
        items = author.generate_items(["food"], 2)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["kind"], "food")

    def test_filters_duplicate_names_within_batch(self):
        client = FakeLlmClient(
            '[{"name": "培元丹", "kind": "pill", "description": "a"}, '
            '{"name": "培元丹", "kind": "pill", "description": "b"}]'
        )
        author = LlmItemAuthor(client)
        items = author.generate_items(["pill"], 2)
        self.assertEqual(len(items), 1)

    def test_non_json_output_yields_empty_list(self):
        client = FakeLlmClient("我不太确定该怎么回答。")
        author = LlmItemAuthor(client)
        self.assertEqual(author.generate_items(["gear"], 3), [])

    def test_missing_description_defaults_to_empty_string(self):
        client = FakeLlmClient('[{"name": "青锋剑", "kind": "gear"}]')
        author = LlmItemAuthor(client)
        items = author.generate_items(["gear"], 1)
        self.assertEqual(items[0]["description"], "")

    def test_blank_kinds_lets_any_valid_kind_through(self):
        """类型留空 = 不限定，不是"没有类型能通过"——空集合当白名单会把所有结果
        都过滤掉，得顶成完整的 ItemKind 集合。"""
        client = FakeLlmClient(
            '[{"name": "青锋剑", "kind": "gear", "description": "锋利"}, '
            '{"name": "灵米粥", "kind": "food", "description": "温补"}]'
        )
        author = LlmItemAuthor(client)
        items = author.generate_items([], 2)
        self.assertEqual(len(items), 2)
        self.assertIn("gear", client.last_prompt)
        self.assertIn("food", client.last_prompt)

    def test_blank_kinds_still_rejects_kind_outside_all_item_kinds(self):
        client = FakeLlmClient('[{"name": "怪物", "kind": "monster", "description": "不该出现"}]')
        author = LlmItemAuthor(client)
        self.assertEqual(author.generate_items([], 1), [])

    def test_all_item_kinds_matches_domain_enum(self):
        from model.domain.items import ItemKind

        self.assertEqual(set(ALL_ITEM_KINDS), {k.value for k in ItemKind})

    def test_novel_reference_included_in_prompt(self):
        client = FakeLlmClient("[]")
        author = LlmItemAuthor(client)
        author.generate_items(["pill"], 1, novel="凡人修仙传")
        self.assertIn("凡人修仙传", client.last_prompt)
        self.assertIn("不要直接使用", client.last_prompt)

    def test_blank_novel_omits_style_reference(self):
        client = FakeLlmClient("[]")
        author = LlmItemAuthor(client)
        author.generate_items(["pill"], 1, novel="")
        self.assertNotIn("请参考小说", client.last_prompt)


if __name__ == "__main__":
    unittest.main()
