import unittest

from model.services.live_narrative_writer import FALLBACK_TEMPLATE, generate_live_variant_text


class FakeLlmClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.last_prompt = None

    def complete(self, prompt: str) -> str:
        self.last_prompt = prompt
        return self.response


class GenerateLiveVariantTextTests(unittest.TestCase):
    def test_none_client_returns_fallback(self):
        text = generate_live_variant_text(None, "some_event", ("生活",))
        self.assertEqual(text, FALLBACK_TEMPLATE.format(event_id="some_event"))

    def test_client_response_is_used(self):
        client = FakeLlmClient("你在酒楼里闲逛，忽然闻到一阵异香。")
        text = generate_live_variant_text(client, "some_event", ("奇遇",))
        self.assertEqual(text, "你在酒楼里闲逛，忽然闻到一阵异香。")

    def test_blank_response_falls_back(self):
        client = FakeLlmClient("   ")
        text = generate_live_variant_text(client, "some_event", ())
        self.assertEqual(text, FALLBACK_TEMPLATE.format(event_id="some_event"))

    def test_client_exception_falls_back_not_raises(self):
        class FailingClient:
            def complete(self, prompt):
                raise ConnectionError("网络超时")

        text = generate_live_variant_text(FailingClient(), "some_event", ())
        self.assertEqual(text, FALLBACK_TEMPLATE.format(event_id="some_event"))

    def test_prompt_includes_event_id_and_tags(self):
        client = FakeLlmClient("文案")
        generate_live_variant_text(client, "cangwu_tavern_fish", ("奇遇", "生活"))
        self.assertIn("cangwu_tavern_fish", client.last_prompt)
        self.assertIn("奇遇", client.last_prompt)
        self.assertIn("生活", client.last_prompt)


if __name__ == "__main__":
    unittest.main()
