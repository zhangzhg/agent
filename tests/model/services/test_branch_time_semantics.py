"""tests/model/services/test_branch_time_semantics.py — "分支不消耗时间"这条产品
决策的看门测试（优化建议.md P1-3）。

背景：对局里有四条结算路径，其中主命令和第二段奇遇会推进游戏时间 + 记事件历史
（`_charge_time`），而分支选项（`_resolve_reply_option`）和流程图节点
（`_advance_scenario`）**故意不推进**。这个差异以前散落在四处重复代码里、谁也没
明说，看起来像疏漏；现在它是明确的决策，由这组测试钉住——如果哪天有人"顺手补上"
分支的计时，这里会红，提醒他先去确认产品意图。
"""
import unittest

from model.domain.events import EventVariant, GameEventDef, ReplyOption
from model.domain.results import StateChange
from model.repositories.sqlite_event_repository import InMemoryEventRepository
from tests.helpers import make_agent, make_play_turn, make_tavern_world


def _event(event_id: str, aliases: tuple, reply_options: tuple = (), duration: int = 2) -> GameEventDef:
    return GameEventDef(
        event_id=event_id,
        applicable_locations=("*",),
        applicable_time=None,
        predicate=None,
        weight=1.0,
        duration_shichen=duration,
        cooldown_shichen=0,
        max_trigger_per_agent=None,
        exclusive_tags=(),
        priority=5,
        tags=("生活",),
        aliases=aliases,
        result_pool=() if reply_options else (StateChange(field="satiety", delta=1),),
        variants=(EventVariant("文案。"),),
        reply_options=reply_options,
        is_command=True,
        is_draft=False,
    )


_OPTIONS = (
    ReplyOption(aliases=("买",), results=(StateChange(field="money", delta=-5),), response_text="你买下了它。"),
    ReplyOption(aliases=("算了",), results=(), response_text="你走开了。"),
)


class BranchTimeSemanticsTests(unittest.TestCase):
    def setUp(self):
        self.events = InMemoryEventRepository({
            "plain": _event("plain", ("吃饭",)),
            "branch": _event("branch", ("看人参",), _OPTIONS),
        })
        self.play_turn = make_play_turn(self.events)
        self.world = make_tavern_world()

    def _elapsed(self, agent, since) -> int:
        return since.shichen_until(agent.time_anchor.current_game_time)

    def test_plain_command_does_consume_time(self):
        """对照组：普通命令按 duration_shichen 推进时间，这条没变。"""
        agent = make_agent(money=100)
        start = agent.time_anchor.current_game_time
        self.play_turn.handle_player_text(agent, self.world, "吃饭")
        self.assertEqual(self._elapsed(agent, start), 2)

    def test_choosing_a_branch_consumes_no_additional_time(self):
        """产品决策：在一个已经发生的场景里做选择，不算又过了一个时辰。"""
        agent = make_agent(money=100)
        start = agent.time_anchor.current_game_time

        self.play_turn.handle_player_text(agent, self.world, "看人参")  # 挂起，等选择
        after_park = self._elapsed(agent, start)
        self.play_turn.handle_player_text(agent, self.world, "买")  # 选中分支

        self.assertEqual(self._elapsed(agent, start), after_park, "选分支不该额外推进时间")
        self.assertEqual(agent.money, 95, "但分支的结果必须照常结算")

    def test_branch_results_still_apply_without_time_cost(self):
        """"不计时"只针对时间，结果池该生效还得生效——别把两件事搞混。"""
        agent = make_agent(money=100)
        self.play_turn.handle_player_text(agent, self.world, "看人参")
        self.play_turn.handle_player_text(agent, self.world, "算了")
        self.assertEqual(agent.money, 100)
        self.assertIsNone(agent.pending_encounter_id)

    def test_branch_events_are_not_recorded_in_history_known_side_effect(self):
        """**已知副作用，非独立决策**：事件历史跟时间推进绑在同一个 `_charge_time`
        里，所以"分支不计时"顺带导致分支型事件不进 `event_history`——它的
        `cooldown_shichen` / `max_trigger_per_agent` 因此都不生效，同一条分支事件
        可以被反复触发。

        这条测试记录**当前事实**，不是在主张它一定对。如果后来决定"分支免费但仍
        然吃冷却"，把 record() 从 `_charge_time` 拆出去、在挂起时调用，然后把这条
        测试改成断言 trigger_count == 1。"""
        agent = make_agent(money=100)
        self.play_turn.handle_player_text(agent, self.world, "看人参")
        self.play_turn.handle_player_text(agent, self.world, "买")

        self.assertEqual(agent.event_history.trigger_count("branch"), 0)

    def test_charge_time_is_not_called_on_branch_resolution(self):
        """直接盯住实现：分支结算路径不得调用 _charge_time。比只看时间数字更能
        定位问题——万一以后 duration 恰好是 0，数字相等会掩盖真正的回归。"""
        agent = make_agent(money=100)
        self.play_turn.handle_player_text(agent, self.world, "看人参")

        calls = []
        original = self.play_turn._charge_time
        self.play_turn._charge_time = lambda *a, **k: calls.append(a) or original(*a, **k)
        self.play_turn.handle_player_text(agent, self.world, "买")

        self.assertEqual(calls, [], "分支结算不该调用 _charge_time")


if __name__ == "__main__":
    unittest.main()
