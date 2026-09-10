import unittest

from model.services.llm_tool_loop import run_tool_loop


class _FakeClient:
    def __init__(self, responses, raises=False):
        self._responses = list(responses)
        self._raises = raises
        self.calls = []

    def complete_with_tools(self, messages, tools):
        self.calls.append((list(messages), tools))
        if self._raises:
            raise RuntimeError("模拟网络失败")
        return self._responses.pop(0)


class RunToolLoopTests(unittest.TestCase):
    def test_no_tool_calls_returns_content_directly(self):
        client = _FakeClient([{"content": "最终答案"}])
        result = run_tool_loop(client, [{"role": "user", "content": "问题"}], [], {})
        self.assertEqual(result, "最终答案")
        self.assertEqual(len(client.calls), 1)

    def test_one_round_of_tool_calls_then_final_answer(self):
        client = _FakeClient([
            {"tool_calls": [{"id": "call_1", "function": {"name": "list_locations", "arguments": "{}"}}]},
            {"content": "查完了，答案是集市"},
        ])
        tool_impls = {"list_locations": lambda: [{"location_id": "market_1", "name": "集市"}]}
        result = run_tool_loop(client, [{"role": "user", "content": "问题"}], [{"type": "function"}], tool_impls)
        self.assertEqual(result, "查完了，答案是集市")
        self.assertEqual(len(client.calls), 2)
        # 第二轮请求里应该包含助手的 tool_calls 消息和工具执行结果
        second_round_messages = client.calls[1][0]
        roles = [m.get("role") for m in second_round_messages]
        self.assertIn("tool", roles)

    def test_tool_result_is_json_serialized_into_message_content(self):
        client = _FakeClient([
            {"tool_calls": [{"id": "call_1", "function": {"name": "list_locations", "arguments": "{}"}}]},
            {"content": "答案"},
        ])
        tool_impls = {"list_locations": lambda: [{"location_id": "market_1", "name": "集市"}]}
        run_tool_loop(client, [{"role": "user", "content": "问题"}], [], tool_impls)
        tool_message = next(m for m in client.calls[1][0] if m.get("role") == "tool")
        self.assertIn("market_1", tool_message["content"])
        self.assertEqual(tool_message["tool_call_id"], "call_1")

    def test_unknown_tool_name_does_not_crash_loop(self):
        client = _FakeClient([
            {"tool_calls": [{"id": "call_1", "function": {"name": "does_not_exist", "arguments": "{}"}}]},
            {"content": "还是给了个答案"},
        ])
        result = run_tool_loop(client, [{"role": "user", "content": "问题"}], [], {})
        self.assertEqual(result, "还是给了个答案")

    def test_tool_impl_exception_does_not_crash_loop(self):
        client = _FakeClient([
            {"tool_calls": [{"id": "call_1", "function": {"name": "boom", "arguments": "{}"}}]},
            {"content": "还是给了个答案"},
        ])
        def _boom():
            raise RuntimeError("工具自己炸了")
        result = run_tool_loop(client, [{"role": "user", "content": "问题"}], [], {"boom": _boom})
        self.assertEqual(result, "还是给了个答案")

    def test_exceeding_max_rounds_returns_none(self):
        # 模型一直要工具、从来不给最终答案
        responses = [{"tool_calls": [{"id": f"call_{i}", "function": {"name": "x", "arguments": "{}"}}]} for i in range(5)]
        client = _FakeClient(responses)
        result = run_tool_loop(client, [{"role": "user", "content": "问题"}], [], {"x": lambda: {}}, max_rounds=3)
        self.assertIsNone(result)
        self.assertEqual(len(client.calls), 3)

    def test_client_exception_returns_none_not_raises(self):
        client = _FakeClient([], raises=True)
        result = run_tool_loop(client, [{"role": "user", "content": "问题"}], [], {})
        self.assertIsNone(result)

    def test_malformed_arguments_json_falls_back_to_empty_dict(self):
        client = _FakeClient([
            {"tool_calls": [{"id": "call_1", "function": {"name": "list_locations", "arguments": "不是JSON"}}]},
            {"content": "答案"},
        ])
        received_args = {}
        def _list_locations(**kwargs):
            received_args.update(kwargs)
            return []
        result = run_tool_loop(client, [{"role": "user", "content": "问题"}], [], {"list_locations": _list_locations})
        self.assertEqual(result, "答案")
        self.assertEqual(received_args, {})


if __name__ == "__main__":
    unittest.main()
