import unittest

from model.repositories.llm.llm_result_text_parser import LlmResultTextParser, ParsedResult


class FakeLlmClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.last_prompt = None

    def complete(self, prompt: str) -> str:
        self.last_prompt = prompt
        return self.response


class LlmResultTextParserTests(unittest.TestCase):
    def test_blank_text_short_circuits_without_calling_client(self):
        client = FakeLlmClient("should never be read")
        parser = LlmResultTextParser(client)
        self.assertEqual(parser.parse("   "), ParsedResult())
        self.assertIsNone(client.last_prompt)

    def test_parses_state_changes(self):
        client = FakeLlmClient('{"state_changes": [{"kind": "state_change", "field": "money", "delta": -5}], "item_query": ""}')
        parser = LlmResultTextParser(client)
        result = parser.parse("花费五两银子买下了金龙鱼")
        self.assertEqual(result.state_changes, [{"kind": "state_change", "field": "money", "delta": -5.0}])
        self.assertEqual(result.item_query, "")

    def test_parses_item_query(self):
        client = FakeLlmClient('{"state_changes": [], "item_query": "一把锋利的长剑"}')
        parser = LlmResultTextParser(client)
        result = parser.parse("你从遗迹里捡到了一把锋利的长剑")
        self.assertEqual(result.item_query, "一把锋利的长剑")
        self.assertEqual(result.state_changes, [])

    def test_strips_markdown_code_fence(self):
        client = FakeLlmClient('```json\n{"state_changes": [{"kind": "state_change", "field": "cultivation", "delta": 5}], "item_query": ""}\n```')
        parser = LlmResultTextParser(client)
        result = parser.parse("修为略有精进")
        self.assertEqual(result.state_changes, [{"kind": "state_change", "field": "cultivation", "delta": 5.0}])

    def test_unsafe_field_filtered_by_shared_sanitizer(self):
        client = FakeLlmClient('{"state_changes": [{"kind": "state_change", "field": "灵气", "delta": 999}], "item_query": ""}')
        parser = LlmResultTextParser(client)
        self.assertEqual(parser.parse("获得大量灵气").state_changes, [])

    def test_non_json_output_yields_empty_result(self):
        client = FakeLlmClient("这句话没有明确的数值得失。")
        parser = LlmResultTextParser(client)
        self.assertEqual(parser.parse("随便逛逛"), ParsedResult())

    def test_json_array_instead_of_object_yields_empty_result(self):
        """旧格式（纯数组）不该被当成新格式误解析——直接当无法解析处理。"""
        client = FakeLlmClient('[{"kind": "state_change", "field": "money", "delta": 5}]')
        parser = LlmResultTextParser(client)
        self.assertEqual(parser.parse("捡到钱了"), ParsedResult())

    def test_no_explicit_effect_returns_empty_result(self):
        client = FakeLlmClient('{"state_changes": [], "item_query": ""}')
        parser = LlmResultTextParser(client)
        self.assertEqual(parser.parse("跟老板寒暄了几句"), ParsedResult())

    def test_prompt_includes_result_text(self):
        client = FakeLlmClient("{}")
        parser = LlmResultTextParser(client)
        parser.parse("花费五两银子买下了金龙鱼")
        self.assertIn("花费五两银子买下了金龙鱼", client.last_prompt)


if __name__ == "__main__":
    unittest.main()
