import unittest

from model.services.world_query_assistant import WorldQueryAssistant, looks_like_info_question
from tests.helpers import make_agent, make_tavern_world


class _FakeToolClient:
    """跟 test_live_content_author.py 的 _FakeToolClient 同一套路：按调用顺序
    依次返回 responses 里的 message 对象。"""

    def __init__(self, responses, raises=False):
        self._responses = list(responses)
        self._raises = raises
        self.calls = []

    def complete_with_tools(self, messages, tools):
        self.calls.append((list(messages), tools))
        if self._raises:
            raise RuntimeError("模拟网络失败")
        return self._responses.pop(0)


class LooksLikeInfoQuestionTests(unittest.TestCase):
    def test_where_am_i_matches(self):
        self.assertTrue(looks_like_info_question("我在哪里"))

    def test_nearest_cities_matches(self):
        self.assertTrue(looks_like_info_question("离我最近的城市有哪些"))

    def test_ordinary_command_does_not_match(self):
        self.assertFalse(looks_like_info_question("吃饭"))
        self.assertFalse(looks_like_info_question("去酒楼打坐"))


class WorldQueryAssistantAnswerTests(unittest.TestCase):
    def test_direct_answer_returned_verbatim(self):
        client = _FakeToolClient([{"content": "你现在在苍梧城，一座热闹的凡人城市。"}])
        assistant = WorldQueryAssistant(client)
        agent = make_agent()
        world = make_tavern_world()

        answer = assistant.answer(agent, world, "我在哪里")

        self.assertEqual(answer, "你现在在苍梧城，一座热闹的凡人城市。")

    def test_tool_call_round_trip_before_final_answer(self):
        client = _FakeToolClient([
            {"tool_calls": [{"id": "call_1", "function": {"name": "get_current_location", "arguments": "{}"}}]},
            {"content": "你现在在醉仙楼附近。"},
        ])
        assistant = WorldQueryAssistant(client)
        agent = make_agent()
        world = make_tavern_world()

        answer = assistant.answer(agent, world, "这是什么地方")

        self.assertEqual(answer, "你现在在醉仙楼附近。")
        self.assertEqual(len(client.calls), 2)
        second_call_messages = client.calls[1][0]
        self.assertTrue(any(m.get("role") == "tool" for m in second_call_messages))

    def test_not_info_query_sentinel_returns_none(self):
        client = _FakeToolClient([{"content": '{"not_info_query": true}'}])
        assistant = WorldQueryAssistant(client)
        agent = make_agent()
        world = make_tavern_world()

        self.assertIsNone(assistant.answer(agent, world, "帮我打个铁匠"))

    def test_client_exception_returns_none_not_raises(self):
        client = _FakeToolClient([], raises=True)
        assistant = WorldQueryAssistant(client)
        agent = make_agent()
        world = make_tavern_world()

        self.assertIsNone(assistant.answer(agent, world, "我在哪里"))

    def test_code_fenced_sentinel_is_still_recognized(self):
        client = _FakeToolClient([{"content": '```json\n{"not_info_query": true}\n```'}])
        assistant = WorldQueryAssistant(client)
        agent = make_agent()
        world = make_tavern_world()

        self.assertIsNone(assistant.answer(agent, world, "帮我打个铁匠"))


if __name__ == "__main__":
    unittest.main()
