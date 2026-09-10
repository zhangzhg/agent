import unittest
from unittest.mock import MagicMock, patch

from model.repositories.llm.llm_config import LlmConnectionConfig
from model.repositories.llm.openai_compatible_client import OpenAiCompatibleClient


def _config() -> LlmConnectionConfig:
    return LlmConnectionConfig(
        provider="glm", base_url="https://example.test/api", model="glm-4-flash",
        api_key="test-key", timeout_seconds=10, embedding_model="embedding-3",
    )


class CompleteWithToolsTests(unittest.TestCase):
    def test_request_body_includes_tools_and_messages(self):
        fake_response = MagicMock()
        fake_response.json.return_value = {"choices": [{"message": {"content": "你好"}}]}
        fake_response.raise_for_status.return_value = None
        with patch("httpx.post", return_value=fake_response) as mock_post:
            client = OpenAiCompatibleClient(_config())
            messages = [{"role": "user", "content": "测试"}]
            tools = [{"type": "function", "function": {"name": "list_locations", "parameters": {}}}]
            result = client.complete_with_tools(messages, tools)

        self.assertEqual(result, {"content": "你好"})
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["json"]["messages"], messages)
        self.assertEqual(kwargs["json"]["tools"], tools)
        self.assertEqual(kwargs["json"]["model"], "glm-4-flash")

    def test_returns_full_message_object_when_tool_calls_present(self):
        """跟 complete() 不同：这里不直接取 content，因为模型要工具时 content
        可能是 None，tool_calls 才是有效载荷——调用方（llm_tool_loop.py）要能
        拿到完整 message 才能判断分支。"""
        fake_response = MagicMock()
        fake_response.json.return_value = {
            "choices": [{"message": {
                "content": None,
                "tool_calls": [{"id": "call_1", "function": {"name": "list_locations", "arguments": "{}"}}],
            }}]
        }
        fake_response.raise_for_status.return_value = None
        with patch("httpx.post", return_value=fake_response):
            client = OpenAiCompatibleClient(_config())
            result = client.complete_with_tools([{"role": "user", "content": "去哪"}], [])

        self.assertIsNone(result["content"])
        self.assertEqual(result["tool_calls"][0]["function"]["name"], "list_locations")

    def test_complete_still_uses_plain_prompt_shape_unaffected(self):
        """complete() 的既有 7 个调用方都不该被这次改动影响。"""
        fake_response = MagicMock()
        fake_response.json.return_value = {"choices": [{"message": {"content": "回答"}}]}
        fake_response.raise_for_status.return_value = None
        with patch("httpx.post", return_value=fake_response) as mock_post:
            client = OpenAiCompatibleClient(_config())
            result = client.complete("你好")

        self.assertEqual(result, "回答")
        _, kwargs = mock_post.call_args
        self.assertNotIn("tools", kwargs["json"])
        self.assertEqual(kwargs["json"]["messages"], [{"role": "user", "content": "你好"}])


if __name__ == "__main__":
    unittest.main()
