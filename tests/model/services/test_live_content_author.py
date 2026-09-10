import unittest

from model.services.live_content_author import LiveContentAuthor


class _FakeClient:
    """author_command_event 用的假客户端——只需要 complete()。"""

    def __init__(self, response=None, raises=False):
        self._response = response
        self._raises = raises
        self.last_prompt = None

    def complete(self, prompt):
        self.last_prompt = prompt
        if self._raises:
            raise RuntimeError("模拟网络失败")
        return self._response


class _FakeToolClient:
    """author_location 用的假客户端——需要 complete_with_tools()，按调用顺序
    依次返回 responses 里的 message 对象（模拟工具调用循环的多轮往返）。"""

    def __init__(self, responses, raises=False):
        self._responses = list(responses)
        self._raises = raises
        self.calls = []

    def complete_with_tools(self, messages, tools):
        self.calls.append((list(messages), tools))
        if self._raises:
            raise RuntimeError("模拟网络失败")
        return self._responses.pop(0)


def _no_locations():
    return []


class AuthorCommandEventTests(unittest.TestCase):
    def test_successful_generation_returns_ready_outcome(self):
        client = _FakeClient(response='[{"tags": ["生活"], "aliases": [], "variants": ["你弹了一曲。"], '
                                        '"weight": 1.0, "duration_shichen": 1, "cooldown_shichen": 0, '
                                        '"priority": 5, "result_pool": [], "item_query": ""}]')
        author = LiveContentAuthor(client)
        outcome = author.author_command_event("我想弹会儿琴", "酒楼")
        self.assertEqual(outcome.kind, "ready")
        self.assertEqual(outcome.command_raw["variants"], ["你弹了一曲。"])

    def test_needs_clarification_outcome(self):
        client = _FakeClient(response='{"needs_clarification": true, "question": "你想对谁做这件事？"}')
        author = LiveContentAuthor(client)
        outcome = author.author_command_event("对他做点什么", "酒楼")
        self.assertEqual(outcome.kind, "needs_clarification")
        self.assertEqual(outcome.question, "你想对谁做这件事？")

    def test_explicit_reject_outcome(self):
        client = _FakeClient(response='{"reject": true}')
        author = LiveContentAuthor(client)
        outcome = author.author_command_event("asdkjhaskjdh", "酒楼")
        self.assertEqual(outcome.kind, "reject")

    def test_malformed_json_returns_reject(self):
        client = _FakeClient(response="不是 JSON")
        author = LiveContentAuthor(client)
        self.assertEqual(author.author_command_event("胡言乱语", "酒楼").kind, "reject")

    def test_client_exception_returns_reject_not_raises(self):
        client = _FakeClient(raises=True)
        author = LiveContentAuthor(client)
        self.assertEqual(author.author_command_event("我想弹会儿琴", "酒楼").kind, "reject")

    def test_empty_variants_returns_reject(self):
        client = _FakeClient(response='[{"tags": [], "aliases": [], "variants": [], "weight": 1.0}]')
        author = LiveContentAuthor(client)
        self.assertEqual(author.author_command_event("胡言乱语", "酒楼").kind, "reject")


class AuthorLocationTests(unittest.TestCase):
    def test_internal_decision_parsed(self):
        client = _FakeToolClient([{"content": '{"name": "藏经阁", "kind": "城市", "is_internal": true}'}])
        author = LiveContentAuthor(client)
        outcome = author.author_location("藏经阁", "苍梧城", "城市", _no_locations)
        self.assertEqual(outcome.kind, "ready")
        self.assertEqual(outcome.location_decision.name, "藏经阁")
        self.assertTrue(outcome.location_decision.is_internal)

    def test_external_decision_parsed(self):
        client = _FakeToolClient([{"content": '{"name": "东海仙岛", "kind": "秘境", "is_internal": false}'}])
        author = LiveContentAuthor(client)
        outcome = author.author_location("东海仙岛", "苍梧城", "城市", _no_locations)
        self.assertEqual(outcome.kind, "ready")
        self.assertFalse(outcome.location_decision.is_internal)

    def test_model_rejects_nonsense_input(self):
        client = _FakeToolClient([{"content": '{"reject": true}'}])
        author = LiveContentAuthor(client)
        self.assertEqual(author.author_location("asdkjhaskjdh", "苍梧城", "城市", _no_locations).kind, "reject")

    def test_needs_clarification_outcome(self):
        client = _FakeToolClient([{"content": '{"needs_clarification": true, "question": "你是想找个僻静角落，还是想去别的城市？"}'}])
        author = LiveContentAuthor(client)
        outcome = author.author_location("别的地方", "苍梧城", "城市", _no_locations)
        self.assertEqual(outcome.kind, "needs_clarification")
        self.assertEqual(outcome.question, "你是想找个僻静角落，还是想去别的城市？")

    def test_kind_outside_whitelist_returns_reject(self):
        client = _FakeToolClient([{"content": '{"name": "藏经阁", "kind": "不存在的类型", "is_internal": true}'}])
        author = LiveContentAuthor(client)
        self.assertEqual(author.author_location("藏经阁", "苍梧城", "城市", _no_locations).kind, "reject")

    def test_malformed_json_returns_reject(self):
        client = _FakeToolClient([{"content": "不是 JSON"}])
        author = LiveContentAuthor(client)
        self.assertEqual(author.author_location("藏经阁", "苍梧城", "城市", _no_locations).kind, "reject")

    def test_client_exception_returns_reject_not_raises(self):
        client = _FakeToolClient([], raises=True)
        author = LiveContentAuthor(client)
        self.assertEqual(author.author_location("藏经阁", "苍梧城", "城市", _no_locations).kind, "reject")

    def test_missing_name_returns_reject(self):
        client = _FakeToolClient([{"content": '{"name": "", "kind": "城市", "is_internal": true}'}])
        author = LiveContentAuthor(client)
        self.assertEqual(author.author_location("藏经阁", "苍梧城", "城市", _no_locations).kind, "reject")

    def test_tool_call_round_trip_resolves_to_existing_location(self):
        """真正的 function calling：模型第一轮要 list_locations，第二轮看到真实
        数据后判断"大集市"其实就是已有的"集市"。"""
        client = _FakeToolClient([
            {"tool_calls": [{"id": "call_1", "function": {"name": "list_locations", "arguments": "{}"}}]},
            {"content": '{"existing_location_id": "market_1"}'},
        ])
        author = LiveContentAuthor(client)
        locations = lambda: [{"location_id": "market_1", "name": "苍梧城·集市", "location_type": "集市"}]
        outcome = author.author_location("大集市", "苍梧城", "城市", locations)
        self.assertEqual(outcome.kind, "ready")
        self.assertEqual(outcome.existing_location_id, "market_1")
        # 第二轮请求里应该能看到工具执行结果被拼回了对话
        self.assertEqual(len(client.calls), 2)
        second_call_messages = client.calls[1][0]
        self.assertTrue(any(m.get("role") == "tool" for m in second_call_messages))


if __name__ == "__main__":
    unittest.main()
