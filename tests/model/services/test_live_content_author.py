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


class _SequencedFakeClient:
    """author_command_event 的补问重试用——第一次 complete() 返回主 prompt 的
    响应（漏填 result_pool），第二次返回补问 prompt 的响应，按调用顺序消费。"""

    def __init__(self, responses):
        self._responses = list(responses)
        self.prompts = []

    def complete(self, prompt):
        self.prompts.append(prompt)
        return self._responses.pop(0)


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
                                        '"priority": 5, "result_pool": [{"kind": "state_change", "field": "satiety", "delta": -1}], '
                                        '"item_query": ""}]')
        author = LiveContentAuthor(client)
        outcome = author.author_command_event("我想弹会儿琴", "酒楼")
        self.assertEqual(outcome.kind, "ready")
        self.assertEqual(outcome.command_raw["variants"], ["你弹了一曲。"])

    def test_empty_result_pool_falls_back_to_default_effect(self):
        """事件触发要有结果，不能"发生了"却什么都没变——prompt 已经要求"至少
        1 条"，但实测这个模型经常直接不给（叙事文案本身是完整的）。跟直接拒绝
        相比，给一个方向稳妥的默认效果更实用，不会因为模型漏填一个字段就把写好
        的叙事整个扔掉。"""
        client = _FakeClient(response='[{"tags": ["生活"], "aliases": [], "variants": ["你弹了一曲。"], '
                                        '"weight": 1.0, "duration_shichen": 1, "cooldown_shichen": 0, '
                                        '"priority": 5, "result_pool": [], "item_query": ""}]')
        author = LiveContentAuthor(client)
        outcome = author.author_command_event("我想弹会儿琴", "酒楼")
        self.assertEqual(outcome.kind, "ready")
        self.assertTrue(outcome.command_raw["result_pool"])

    def test_empty_result_pool_retries_narrowly_before_defaulting(self):
        """漏填 result_pool 时，先窄范围补问一次（只让模型针对已经写好的叙事单独
        回答 result_pool），补问给出了有效结果就该用补问的，不是直接落到默认值
        （默认值只是补问也拿不到时的最后一道防线）。"""
        client = _SequencedFakeClient([
            '[{"tags": ["生活"], "aliases": [], "variants": ["你弹了一曲。"], '
            '"weight": 1.0, "duration_shichen": 1, "cooldown_shichen": 0, '
            '"priority": 5, "result_pool": [], "item_query": ""}]',
            '{"result_pool": [{"kind": "state_change", "field": "satiety", "delta": -3}]}',
        ])
        author = LiveContentAuthor(client)
        outcome = author.author_command_event("我想弹会儿琴", "酒楼")
        self.assertEqual(outcome.kind, "ready")
        self.assertEqual(
            outcome.command_raw["result_pool"],
            [{"kind": "state_change", "field": "satiety", "delta": -3}],
        )
        self.assertEqual(len(client.prompts), 2)

    def test_empty_result_pool_retry_also_empty_falls_back_to_default(self):
        client = _SequencedFakeClient([
            '[{"tags": ["生活"], "aliases": [], "variants": ["你弹了一曲。"], '
            '"weight": 1.0, "duration_shichen": 1, "cooldown_shichen": 0, '
            '"priority": 5, "result_pool": [], "item_query": ""}]',
            '{"result_pool": []}',
        ])
        author = LiveContentAuthor(client)
        outcome = author.author_command_event("我想弹会儿琴", "酒楼")
        self.assertEqual(outcome.kind, "ready")
        self.assertTrue(outcome.command_raw["result_pool"])  # 落到默认效果，不是空

    def test_deferred_result_pool_extracted_when_present(self):
        client = _FakeClient(response='[{"tags": ["社交"], "aliases": [], "variants": ["你帮了个忙。"], '
                                        '"weight": 1.0, "duration_shichen": 1, "cooldown_shichen": 0, '
                                        '"priority": 5, "result_pool": [{"kind": "state_change", "field": "money", "delta": 3}], '
                                        '"deferred_result_pool": [{"kind": "state_change", "field": "heart_demon", "delta": -0.02}], '
                                        '"item_query": ""}]')
        author = LiveContentAuthor(client)
        outcome = author.author_command_event("帮个忙", "酒楼")
        self.assertEqual(
            outcome.command_raw["deferred_result_pool"],
            [{"kind": "state_change", "field": "heart_demon", "delta": -0.02}],
        )

    def test_deferred_result_pool_defaults_to_empty_when_absent(self):
        """绝大多数动作没有"当下还没兑现"的另一面影响——不给这个字段是正常情况，
        不该像 result_pool 那样触发补问/默认值兜底。"""
        client = _FakeClient(response='[{"tags": ["生活"], "aliases": [], "variants": ["你弹了一曲。"], '
                                        '"weight": 1.0, "duration_shichen": 1, "cooldown_shichen": 0, '
                                        '"priority": 5, "result_pool": [{"kind": "state_change", "field": "satiety", "delta": -1}], '
                                        '"item_query": ""}]')
        author = LiveContentAuthor(client)
        outcome = author.author_command_event("我想弹会儿琴", "酒楼")
        self.assertEqual(outcome.command_raw["deferred_result_pool"], [])

    def test_deferred_result_pool_filters_unsafe_entries_same_as_result_pool(self):
        client = _FakeClient(response='[{"tags": ["社交"], "aliases": [], "variants": ["你帮了个忙。"], '
                                        '"weight": 1.0, "duration_shichen": 1, "cooldown_shichen": 0, '
                                        '"priority": 5, "result_pool": [{"kind": "state_change", "field": "money", "delta": 3}], '
                                        '"deferred_result_pool": [{"kind": "item_drop", "item_id": "x", "n": 1}], '
                                        '"item_query": ""}]')
        author = LiveContentAuthor(client)
        outcome = author.author_command_event("帮个忙", "酒楼")
        self.assertEqual(outcome.command_raw["deferred_result_pool"], [])

    def test_branching_reply_options_parsed_and_result_pool_forced_empty(self):
        client = _FakeClient(response='[{"tags": ["经济"], "aliases": [], '
                                        '"variants": ["你在集市看到有人卖百年人参。"], '
                                        '"weight": 1.0, "duration_shichen": 1, "cooldown_shichen": 0, '
                                        '"priority": 5, "result_pool": [{"kind": "state_change", "field": "money", "delta": -999}], '
                                        '"reply_options": ['
                                        '{"aliases": ["买", "买下来"], "response_text": "你付了钱，把人参收好。", '
                                        '"results": [{"kind": "item_drop", "item_id": "百年人参", "n": 1}, '
                                        '{"kind": "state_change", "field": "money", "delta": -50}]}, '
                                        '{"aliases": ["算了", "不买"], "response_text": "你看了一眼，摇摇头走开了。", '
                                        '"results": []}'
                                        '], "item_query": ""}]')
        author = LiveContentAuthor(client)
        outcome = author.author_command_event("我在集市看到有人卖百年人参", "集市")

        self.assertEqual(outcome.kind, "ready")
        # 有分支时顶层 result_pool 强制清空，不会用到（哪怕模型给了内容）。
        self.assertEqual(outcome.command_raw["result_pool"], [])
        options = outcome.command_raw["reply_options"]
        self.assertEqual(len(options), 2)
        self.assertEqual(options[0]["aliases"], ["买", "买下来"])
        self.assertEqual(
            options[0]["results"],
            [{"kind": "item_drop", "item_id": "百年人参", "n": 1}, {"kind": "state_change", "field": "money", "delta": -50}],
        )
        self.assertEqual(options[1]["results"], [])

    def test_single_branch_does_not_count_as_branching(self):
        """只有 1 个分支等于没得选，不该退化成伪分支——按普通 result_pool 处理。"""
        client = _FakeClient(response='[{"tags": ["生活"], "aliases": [], "variants": ["你弹了一曲。"], '
                                        '"weight": 1.0, "duration_shichen": 1, "cooldown_shichen": 0, "priority": 5, '
                                        '"result_pool": [{"kind": "state_change", "field": "satiety", "delta": -1}], '
                                        '"reply_options": [{"aliases": ["继续"], "response_text": "", "results": []}], '
                                        '"item_query": ""}]')
        author = LiveContentAuthor(client)
        outcome = author.author_command_event("我想弹会儿琴", "酒楼")

        self.assertEqual(outcome.command_raw["reply_options"], [])
        self.assertEqual(outcome.command_raw["result_pool"], [{"kind": "state_change", "field": "satiety", "delta": -1}])

    def test_branch_option_missing_aliases_is_dropped(self):
        client = _FakeClient(response='[{"tags": ["经济"], "aliases": [], "variants": ["你看到一件东西。"], '
                                        '"weight": 1.0, "duration_shichen": 1, "cooldown_shichen": 0, "priority": 5, '
                                        '"result_pool": [], "reply_options": ['
                                        '{"aliases": ["买"], "response_text": "", "results": []}, '
                                        '{"aliases": [], "response_text": "", "results": []}, '
                                        '{"aliases": ["走"], "response_text": "", "results": []}'
                                        '], "item_query": ""}]')
        author = LiveContentAuthor(client)
        outcome = author.author_command_event("我看到一件东西", "集市")

        self.assertEqual(len(outcome.command_raw["reply_options"]), 2)

    def test_no_reply_options_field_behaves_like_before(self):
        client = _FakeClient(response='[{"tags": ["生活"], "aliases": [], "variants": ["你弹了一曲。"], '
                                        '"weight": 1.0, "duration_shichen": 1, "cooldown_shichen": 0, "priority": 5, '
                                        '"result_pool": [{"kind": "state_change", "field": "satiety", "delta": -1}], '
                                        '"item_query": ""}]')
        author = LiveContentAuthor(client)
        outcome = author.author_command_event("我想弹会儿琴", "酒楼")

        self.assertEqual(outcome.command_raw["reply_options"], [])

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

    def test_echoed_prompt_placeholder_variant_is_rejected(self):
        """实测偶尔会照抄 prompt 里 JSON 示例的占位描述文字本身（"第二人称叙事
        文案，40-120字，古风白话文风格"），而不是替换成真正的场景文案——这种
        半成品绝不能原样发给玩家，宁可整条拒绝，回落到兜底链的下一层。"""
        client = _FakeClient(response='[{"tags": ["生活"], "aliases": [], '
                                        '"variants": ["第二人称叙事文案，40-120字，古风白话文风格"], '
                                        '"weight": 1.0, "duration_shichen": 1, "cooldown_shichen": 0, "priority": 5, '
                                        '"result_pool": [{"kind": "state_change", "field": "satiety", "delta": -5}], '
                                        '"item_query": ""}]')
        author = LiveContentAuthor(client)
        self.assertEqual(author.author_command_event("路边有个可疑的人在招手", "集市").kind, "reject")


class CheckStorylineConcludedTests(unittest.TestCase):
    def test_concluded_true_parsed(self):
        client = _FakeClient(response='{"concluded": true}')
        author = LiveContentAuthor(client)
        self.assertTrue(author.check_storyline_concluded("之前的伏笔", "算了不管了"))

    def test_concluded_false_parsed(self):
        client = _FakeClient(response='{"concluded": false}')
        author = LiveContentAuthor(client)
        self.assertFalse(author.check_storyline_concluded("之前的伏笔", "后来呢"))

    def test_malformed_json_defaults_to_not_concluded(self):
        client = _FakeClient(response="不是 JSON")
        author = LiveContentAuthor(client)
        self.assertFalse(author.check_storyline_concluded("之前的伏笔", "随便说点什么"))

    def test_client_exception_defaults_to_not_concluded(self):
        client = _FakeClient(raises=True)
        author = LiveContentAuthor(client)
        self.assertFalse(author.check_storyline_concluded("之前的伏笔", "随便说点什么"))


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
