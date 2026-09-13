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


class MoveMustNotSwallowCommandsTests(unittest.TestCase):
    """回归测试：移动的"去"是全文搜索，一度排在事件别名表之前，把任何含"去"的
    句子都吞成移动——"去吃点东西"（EAT 自己注册的别名）被解析成"移动到『吃点
    东西』"，别名成了永远匹配不上的死代码，README §1.13 那条四层兜底链也整个
    被截胡。现在别名表排在移动之前。"""

    def setUp(self):
        self.parser = ChatParser({
            "吃饭": "eat", "去吃点东西": "eat", "果腹": "eat",
            "打坐": "meditate", "运功": "meditate", "修炼": "meditate",
            "闲逛": "idle_wander", "到处走走": "idle_wander",
        })

    def test_registered_alias_containing_qu_is_not_parsed_as_move(self):
        cmd = self.parser.parse("去吃点东西")
        self.assertEqual(cmd.event_id, "eat")

    def test_verb_prefix_qu_does_not_hijack_command(self):
        for text, expected in [
            ("我想去打坐", "meditate"),
            ("我打算去修炼一下", "meditate"),
            ("出去到处走走", "idle_wander"),
        ]:
            with self.subTest(text=text):
                self.assertEqual(self.parser.parse(text).event_id, expected)

    def test_location_prefix_is_kept_when_alias_matches(self):
        """README 1.11 的例子："去酒楼吃饭" → 地点=酒楼、行动=eat。"""
        cmd = self.parser.parse("去酒楼吃饭")
        self.assertEqual(cmd.event_id, "eat")
        self.assertEqual(cmd.location_hint, "酒楼")

    def test_retreat_still_wins_over_overlapping_meditate_alias(self):
        """"闭关修炼"里含着 MEDITATE 的别名"修炼"——系统命令必须仍排在别名表之前。"""
        cmd = self.parser.parse("闭关修炼")
        self.assertEqual(cmd.event_id, "retreat_start")

    def test_grammatical_particles_are_not_treated_as_destinations(self):
        """"我不想去了"切出的"了"、"回去吧"切出的"去吧"都不是地名。放行的话
        PlayTurnService 会拿它去调 LiveContentAuthor 实时创作一个叫"了"的地点
        并写进世界快照（解析 bug 传导成持久化数据污染）。"""
        for text in ["我不想去了", "他走过去了", "回去吧"]:
            with self.subTest(text=text):
                self.assertIsNone(self.parser.parse(text))


class SeededAliasReachabilityTests(unittest.TestCase):
    """内容库里注册的每一个命令别名，都必须能被 ChatParser 解析回它自己——
    "注册了却永远匹配不上"这类死别名，以后由这条测试自动发现，不用再靠人肉试。"""

    def test_every_seeded_command_alias_resolves_to_its_own_event(self):
        from content.events import commands

        alias_map = {a: e.event_id for e in commands.ALL for a in e.aliases}
        parser = ChatParser(alias_map)
        for defn in commands.ALL:
            for alias in defn.aliases:
                with self.subTest(event_id=defn.event_id, alias=alias):
                    cmd = parser.parse(alias)
                    self.assertIsNotNone(cmd, f"别名 {alias!r} 解析不出任何命令")
                    self.assertEqual(cmd.event_id, defn.event_id)


if __name__ == "__main__":
    unittest.main()
