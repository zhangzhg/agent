import unittest

from model.services.result_pool_safety import SAFE_STATE_CHANGE_FIELDS, sanitize_branch_results, sanitize_result_pool


class SanitizeResultPoolTests(unittest.TestCase):
    def test_valid_state_change_passes_through(self):
        result = sanitize_result_pool([{"kind": "state_change", "field": "money", "delta": 5}])
        self.assertEqual(result, [{"kind": "state_change", "field": "money", "delta": 5.0}])

    def test_extreme_delta_is_clamped_not_dropped(self):
        """实测 glm-4-flash 有时会给出远超"常见范围"提示的数值（比如买一件贵重
        物品直接给 money delta -200），放行会让单次事件把玩家的钱清空——clamp
        到安全上限，而不是整条丢弃（丢弃会导致"发生了"却"什么都没变"，clamp
        既保住了"这次变化比较大"的方向，又不会离谱到破坏数值平衡）。"""
        result = sanitize_result_pool([{"kind": "state_change", "field": "money", "delta": -200}])
        self.assertEqual(result, [{"kind": "state_change", "field": "money", "delta": -60.0}])

        result = sanitize_result_pool([{"kind": "state_change", "field": "heart_demon", "delta": 5}])
        self.assertEqual(result, [{"kind": "state_change", "field": "heart_demon", "delta": 0.2}])

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


class SanitizeBranchResultsTests(unittest.TestCase):
    def test_state_change_and_item_drop_both_pass_through(self):
        result = sanitize_branch_results([
            {"kind": "state_change", "field": "money", "delta": -30},
            {"kind": "item_drop", "item_id": "百年人参", "n": 1},
        ])
        self.assertEqual(result, [
            {"kind": "state_change", "field": "money", "delta": -30.0},
            {"kind": "item_drop", "item_id": "百年人参", "n": 1},
        ])

    def test_item_drop_does_not_require_known_item_id(self):
        """分支结果是这次对局临时创作的产物（跟事件本身的 live_xxxxx id 一样不经
        草稿审核），item_id 不用是游戏里已登记的物品——Inventory 只是个
        id->count 字典，未登记的 item_id 会被背包面板直接当显示名用。"""
        result = sanitize_branch_results([{"kind": "item_drop", "item_id": "从没听过的东西", "n": 1}])
        self.assertEqual(result, [{"kind": "item_drop", "item_id": "从没听过的东西", "n": 1}])

    def test_item_drop_missing_item_id_dropped(self):
        result = sanitize_branch_results([{"kind": "item_drop", "n": 1}])
        self.assertEqual(result, [])

    def test_item_drop_count_clamped(self):
        result = sanitize_branch_results([{"kind": "item_drop", "item_id": "x", "n": 999}])
        self.assertEqual(result, [{"kind": "item_drop", "item_id": "x", "n": 5}])

    def test_unsafe_state_change_field_dropped(self):
        result = sanitize_branch_results([{"kind": "state_change", "field": "灵气", "delta": 5}])
        self.assertEqual(result, [])

    def test_other_kinds_dropped(self):
        result = sanitize_branch_results([{"kind": "chain_event", "event_id": "x"}])
        self.assertEqual(result, [])

    def test_extreme_delta_is_clamped(self):
        result = sanitize_branch_results([{"kind": "state_change", "field": "money", "delta": -200}])
        self.assertEqual(result, [{"kind": "state_change", "field": "money", "delta": -60.0}])

    def test_non_list_input_returns_empty(self):
        self.assertEqual(sanitize_branch_results(None), [])
        self.assertEqual(sanitize_branch_results("not a list"), [])


if __name__ == "__main__":
    unittest.main()
