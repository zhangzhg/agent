"""tests/model/services/test_llm_call_budget.py — 单回合大模型调用预算
（优化建议.md P1-4）。

一次玩家输入最坏情况下会串行发起多次大模型往返（伏笔收尾判断 → 实时创作 →
result_pool 补问 → 地点创作的工具循环 → 补叙事文案），全部同步阻塞。预算用完
之后必须走各调用点本来就有的降级路径，而不是继续打下去、让玩家干等。
"""
import unittest

from model.services.live_authoring_coordinator import LiveAuthoringCoordinator, LlmCallBudget, _BudgetedClient
from model.repositories.sqlite_event_repository import InMemoryEventRepository
from tests.helpers import make_agent, make_tavern_world


class _CountingClient:
    def __init__(self, response: str = "not json"):
        self.calls = 0
        self.response = response

    def complete(self, prompt):
        self.calls += 1
        return self.response

    def complete_with_tools(self, messages, tools):
        self.calls += 1
        return {"content": self.response}


class LlmCallBudgetTests(unittest.TestCase):
    def test_not_exhausted_before_limit(self):
        budget = LlmCallBudget(max_calls=3)
        budget.start()
        for _ in range(3):
            self.assertFalse(budget.exhausted())
            budget.consume()
        self.assertTrue(budget.exhausted())

    def test_time_limit_triggers_exhaustion(self):
        budget = LlmCallBudget(max_calls=99, max_seconds=-1.0)  # 负数 = 立刻算超时
        budget.start()
        self.assertTrue(budget.exhausted())

    def test_start_resets_previous_turns_usage(self):
        budget = LlmCallBudget(max_calls=2)
        budget.start()
        budget.consume()
        budget.consume()
        self.assertTrue(budget.exhausted())
        budget.start()
        self.assertFalse(budget.exhausted())


class BudgetedClientTests(unittest.TestCase):
    def test_passes_through_until_budget_runs_out(self):
        inner = _CountingClient()
        budget = LlmCallBudget(max_calls=2)
        budget.start()
        client = _BudgetedClient(inner, budget)

        client.complete("a")
        client.complete("b")
        with self.assertRaises(RuntimeError):
            client.complete("c")
        self.assertEqual(inner.calls, 2)

    def test_tool_calls_share_the_same_budget(self):
        """工具循环的多轮往返也要计入同一份预算，否则一次 function calling 就能
        绕过上限打满三轮。"""
        inner = _CountingClient()
        budget = LlmCallBudget(max_calls=1)
        budget.start()
        client = _BudgetedClient(inner, budget)

        client.complete_with_tools([], [])
        with self.assertRaises(RuntimeError):
            client.complete_with_tools([], [])
        self.assertEqual(inner.calls, 1)


class CoordinatorBudgetIntegrationTests(unittest.TestCase):
    def test_exhausted_budget_degrades_to_reject_instead_of_raising(self):
        """预算用尽后，协调器必须返回 reject（调用方本来就会处理的降级形态），
        而不是把 RuntimeError 抛到回合外面去。"""
        inner = _CountingClient()
        coord = LiveAuthoringCoordinator(InMemoryEventRepository(), inner)
        coord.begin_turn()
        coord._budget.max_calls = 1

        agent = make_agent()
        first = coord.author_command(agent, "我想弹会儿琴")
        second = coord.author_command(agent, "我想再弹一曲")

        self.assertEqual(inner.calls, 1)  # 第二次压根没打出去
        self.assertEqual(second.kind, "reject")
        self.assertIsNotNone(first)

    def test_begin_turn_gives_each_turn_a_fresh_budget(self):
        inner = _CountingClient()
        coord = LiveAuthoringCoordinator(InMemoryEventRepository(), inner)
        coord.begin_turn()
        coord._budget.max_calls = 1
        coord.author_command(make_agent(), "第一回合")
        self.assertEqual(inner.calls, 1)

        coord.begin_turn()  # 新回合，预算重置
        coord.author_command(make_agent(), "第二回合")
        self.assertEqual(inner.calls, 2)

    def test_destination_authoring_also_respects_budget(self):
        inner = _CountingClient()
        coord = LiveAuthoringCoordinator(InMemoryEventRepository(), inner)
        coord.begin_turn()
        coord._budget.max_calls = 0

        outcome = coord.author_destination(make_agent(), make_tavern_world(), "一个没听过的地方")

        self.assertEqual(inner.calls, 0)
        self.assertEqual(outcome.kind, "reject")

    def test_no_llm_configured_still_works(self):
        coord = LiveAuthoringCoordinator(InMemoryEventRepository(), None)
        coord.begin_turn()
        self.assertFalse(coord.enabled)
        self.assertEqual(coord.author_command(make_agent(), "随便说点什么").kind, "reject")


if __name__ == "__main__":
    unittest.main()
