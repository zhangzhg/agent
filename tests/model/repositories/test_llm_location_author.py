import unittest

from model.repositories.llm.llm_location_author import LlmLocationAuthor


class FakeLlmClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.last_prompt = None

    def complete(self, prompt: str) -> str:
        self.last_prompt = prompt
        return self.response


class LlmLocationAuthorTests(unittest.TestCase):
    def test_parses_valid_json_array(self):
        client = FakeLlmClient('[{"name": "苍梧城", "kind": "城市"}, {"name": "黑风谷", "kind": "荒野"}]')
        author = LlmLocationAuthor(client)
        items = author.generate_locations(["城市", "荒野"], 2)
        self.assertEqual(items, [{"name": "苍梧城", "kind": "城市"}, {"name": "黑风谷", "kind": "荒野"}])

    def test_strips_markdown_code_fence(self):
        client = FakeLlmClient('```json\n[{"name": "藏剑山门", "kind": "山门"}]\n```')
        author = LlmLocationAuthor(client)
        items = author.generate_locations(["山门"], 1)
        self.assertEqual(items, [{"name": "藏剑山门", "kind": "山门"}])

    def test_filters_kind_outside_whitelist(self):
        client = FakeLlmClient('[{"name": "落雁镇", "kind": "城市"}, {"name": "怪东西", "kind": "海洋"}]')
        author = LlmLocationAuthor(client)
        items = author.generate_locations(["城市"], 2)
        self.assertEqual(items, [{"name": "落雁镇", "kind": "城市"}])

    def test_filters_duplicate_names_within_batch(self):
        client = FakeLlmClient('[{"name": "苍梧城", "kind": "城市"}, {"name": "苍梧城", "kind": "城市"}]')
        author = LlmLocationAuthor(client)
        items = author.generate_locations(["城市"], 2)
        self.assertEqual(items, [{"name": "苍梧城", "kind": "城市"}])

    def test_non_json_output_yields_empty_list(self):
        client = FakeLlmClient("抱歉，我无法完成这个请求。")
        author = LlmLocationAuthor(client)
        self.assertEqual(author.generate_locations(["城市"], 3), [])

    def test_single_object_instead_of_array_is_accepted(self):
        client = FakeLlmClient('{"name": "云归镇", "kind": "城市"}')
        author = LlmLocationAuthor(client)
        items = author.generate_locations(["城市"], 1)
        self.assertEqual(items, [{"name": "云归镇", "kind": "城市"}])

    def test_prompt_includes_count_and_kinds(self):
        client = FakeLlmClient("[]")
        author = LlmLocationAuthor(client)
        author.generate_locations(["城市", "荒野"], 4)
        self.assertIn("4", client.last_prompt)
        self.assertIn("城市", client.last_prompt)
        self.assertIn("荒野", client.last_prompt)


if __name__ == "__main__":
    unittest.main()
