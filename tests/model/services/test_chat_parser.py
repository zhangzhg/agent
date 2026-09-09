import unittest

from model.services.chat_parser import MOVE_EVENT_ID, ChatParser


class MoveParsingTests(unittest.TestCase):
    """_MOVE_PATTERN 曾经锚在句首，"我想去X"这类自然语言包裹完全进不了 move
    分支，直接落到"听不懂"——这里覆盖放宽后的行为。"""

    def setUp(self):
        self.parser = ChatParser(alias_to_event_id={"吃饭": "eat"})

    def test_prefix_at_start_still_matches(self):
        cmd = self.parser.parse("去集市")
        self.assertEqual(cmd.event_id, MOVE_EVENT_ID)
        self.assertEqual(cmd.location_hint, "集市")

    def test_wrapped_in_natural_language_now_matches(self):
        cmd = self.parser.parse("我想去其他城市")
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd.event_id, MOVE_EVENT_ID)
        self.assertEqual(cmd.location_hint, "其他城市")

    def test_qianwang_wrapped_in_natural_language_matches(self):
        cmd = self.parser.parse("能不能带我前往集市")
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd.event_id, MOVE_EVENT_ID)
        self.assertEqual(cmd.location_hint, "集市")

    def test_hui_prefix_at_start_still_matches(self):
        cmd = self.parser.parse("回城门")
        self.assertEqual(cmd.event_id, MOVE_EVENT_ID)
        self.assertEqual(cmd.location_hint, "城门")

    def test_hui_wrapped_in_natural_language_is_a_known_limitation(self):
        """"回"故意没放宽（常见于否定句，"我不想回去"之类）——这里只是记录已知
        局限，不是这次改动的验收标准。"""
        cmd = self.parser.parse("我想回城门")
        self.assertIsNone(cmd)

    def test_alias_matching_still_works_unaffected(self):
        cmd = self.parser.parse("吃饭")
        self.assertEqual(cmd.event_id, "eat")

    def test_unrelated_text_still_returns_none(self):
        self.assertIsNone(self.parser.parse("今天天气怎么样"))


if __name__ == "__main__":
    unittest.main()
