import unittest

from model.services.live_content_author import LiveContentAuthor


class _FakeClient:
    def __init__(self, response=None, raises=False):
        self._response = response
        self._raises = raises
        self.last_prompt = None

    def complete(self, prompt):
        self.last_prompt = prompt
        if self._raises:
            raise RuntimeError("模拟网络失败")
        return self._response


class AuthorCommandEventTests(unittest.TestCase):
    def test_successful_generation_returns_flavor_dict(self):
        client = _FakeClient(response='[{"tags": ["生活"], "aliases": [], "variants": ["你弹了一曲。"], '
                                        '"weight": 1.0, "duration_shichen": 1, "cooldown_shichen": 0, '
                                        '"priority": 5, "result_pool": [], "item_query": ""}]')
        author = LiveContentAuthor(client)
        result = author.author_command_event("我想弹会儿琴", "酒楼")
        self.assertIsNotNone(result)
        self.assertEqual(result["variants"], ["你弹了一曲。"])

    def test_malformed_json_returns_none(self):
        client = _FakeClient(response="不是 JSON")
        author = LiveContentAuthor(client)
        self.assertIsNone(author.author_command_event("胡言乱语", "酒楼"))

    def test_client_exception_returns_none_not_raises(self):
        client = _FakeClient(raises=True)
        author = LiveContentAuthor(client)
        self.assertIsNone(author.author_command_event("我想弹会儿琴", "酒楼"))

    def test_empty_variants_returns_none(self):
        client = _FakeClient(response='[{"tags": [], "aliases": [], "variants": [], "weight": 1.0}]')
        author = LiveContentAuthor(client)
        self.assertIsNone(author.author_command_event("胡言乱语", "酒楼"))


class AuthorLocationTests(unittest.TestCase):
    def test_internal_decision_parsed(self):
        client = _FakeClient(response='{"name": "藏经阁", "kind": "城市", "is_internal": true}')
        author = LiveContentAuthor(client)
        decision = author.author_location("藏经阁", "苍梧城", "城市")
        self.assertIsNotNone(decision)
        self.assertEqual(decision.name, "藏经阁")
        self.assertTrue(decision.is_internal)

    def test_external_decision_parsed(self):
        client = _FakeClient(response='{"name": "东海仙岛", "kind": "秘境", "is_internal": false}')
        author = LiveContentAuthor(client)
        decision = author.author_location("东海仙岛", "苍梧城", "城市")
        self.assertIsNotNone(decision)
        self.assertFalse(decision.is_internal)

    def test_model_rejects_nonsense_input(self):
        client = _FakeClient(response='{"reject": true}')
        author = LiveContentAuthor(client)
        self.assertIsNone(author.author_location("asdkjhaskjdh", "苍梧城", "城市"))

    def test_kind_outside_whitelist_returns_none(self):
        client = _FakeClient(response='{"name": "藏经阁", "kind": "不存在的类型", "is_internal": true}')
        author = LiveContentAuthor(client)
        self.assertIsNone(author.author_location("藏经阁", "苍梧城", "城市"))

    def test_malformed_json_returns_none(self):
        client = _FakeClient(response="不是 JSON")
        author = LiveContentAuthor(client)
        self.assertIsNone(author.author_location("藏经阁", "苍梧城", "城市"))

    def test_client_exception_returns_none_not_raises(self):
        client = _FakeClient(raises=True)
        author = LiveContentAuthor(client)
        self.assertIsNone(author.author_location("藏经阁", "苍梧城", "城市"))

    def test_missing_name_returns_none(self):
        client = _FakeClient(response='{"name": "", "kind": "城市", "is_internal": true}')
        author = LiveContentAuthor(client)
        self.assertIsNone(author.author_location("藏经阁", "苍梧城", "城市"))


if __name__ == "__main__":
    unittest.main()
