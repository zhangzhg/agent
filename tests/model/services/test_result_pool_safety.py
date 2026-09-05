import unittest

from model.services.result_pool_safety import SAFE_STATE_CHANGE_FIELDS, sanitize_result_pool


class SanitizeResultPoolTests(unittest.TestCase):
    def test_valid_state_change_passes_through(self):
        result = sanitize_result_pool([{"kind": "state_change", "field": "money", "delta": 5}])
        self.assertEqual(result, [{"kind": "state_change", "field": "money", "delta": 5.0}])

    def test_non_list_input_returns_empty(self):
        self.assertEqual(sanitize_result_pool(None), [])
        self.assertEqual(sanitize_result_pool("not a list"), [])
        self.assertEqual(sanitize_result_pool({"kind": "state_change"}), [])

    def test_non_state_change_kind_dropped(self):
        result = sanitize_result_pool([{"kind": "item_drop", "item_id": "不存在的物品", "n": 1}])
        self.assertEqual(result, [])

    def test_unsafe_field_name_dropped(self):
        result = sanitize_result_pool([{"kind": "state_change", "field": "灵气", "delta": 5}])
        self.assertEqual(result, [])

    def test_non_numeric_delta_dropped(self):
        result = sanitize_result_pool([{"kind": "state_change", "field": "money", "delta": "很多"}])
        self.assertEqual(result, [])

    def test_missing_delta_dropped(self):
        result = sanitize_result_pool([{"kind": "state_change", "field": "money"}])
        self.assertEqual(result, [])

    def test_capped_at_three_entries(self):
        entries = [{"kind": "state_change", "field": "money", "delta": 1} for _ in range(6)]
        self.assertEqual(len(sanitize_result_pool(entries)), 3)

    def test_all_safe_fields_are_agent_domain_fields(self):
        """交叉检查：白名单字段名必须是 Agent 数据类上真实存在的属性——否则
        ResultPoolExecutor 的 setattr(agent, field, ...) 会在触发时 AttributeError。"""
        from dataclasses import fields

        from model.domain.agent import Agent

        agent_field_names = {f.name for f in fields(Agent)}
        self.assertTrue(set(SAFE_STATE_CHANGE_FIELDS).issubset(agent_field_names))


if __name__ == "__main__":
    unittest.main()
