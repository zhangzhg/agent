import unittest
from dataclasses import replace

from model.domain.events import EventVariant, GameEventDef, GameEventOccurrence, ReplyOption, TriggerSource
from model.domain.predicates import Predicate, PredicateGroup, PredicateType
from model.domain.results import ItemDrop, StateChange
from model.domain.states import ActingState, ClosedDoorState, DeadState, EncounterPendingState
from model.repositories.event_log import InMemoryEventLogStore
from model.repositories.sqlite_event_repository import InMemoryEventRepository
from model.services.arbiter import ArbitrationDecision
from tests.helpers import make_agent, make_play_turn, make_tavern_world, make_time


def _command(event_id="eat", predicate=None, result_pool=(), aliases=("吃饭",)):
    return GameEventDef(
        event_id=event_id,
        applicable_locations=("*",),
        applicable_time=None,
        predicate=predicate,
        weight=1.0,
        duration_shichen=1,
        cooldown_shichen=0,
        max_trigger_per_agent=None,
        exclusive_tags=(),
        priority=5,
        tags=("生活",),
        aliases=aliases,
        result_pool=result_pool,
        variants=(EventVariant("你吃了饭。"),),
        is_command=True,
        is_draft=False,
    )


def _encounter(event_id="fish", weight=100.0, needs_reply_options=()):
    return GameEventDef(
        event_id=event_id,
        applicable_locations=("酒楼",),
        applicable_time=None,
        predicate=None,
        weight=weight,
        duration_shichen=1,
        cooldown_shichen=0,
        max_trigger_per_agent=None,
        exclusive_tags=(),
        priority=5,
        tags=("奇遇",),
        aliases=(),
        result_pool=(ItemDrop("gold", 1),) if not needs_reply_options else (),
        variants=(EventVariant("水缸里有条金龙鱼！"),),
        reply_options=needs_reply_options,
        is_command=False,
        is_draft=False,
    )


class PredicateFailureTests(unittest.TestCase):
    def test_predicate_failure_keeps_idle_no_diff_no_log(self):
        events = InMemoryEventRepository({"eat": _command(predicate=PredicateGroup("AND", (Predicate(PredicateType.MONEY_GTE, (999,)),)))})
        log = InMemoryEventLogStore()
        play_turn = make_play_turn(events, log=log)
        agent = make_agent(money=1)
        world = make_tavern_world()

        result = play_turn.handle_player_text(agent, world, "吃饭")

        self.assertEqual(result.reject_reason, "条件未满足。")
        self.assertEqual(agent.state.name, "idle")
        self.assertEqual(agent.money, 1)
        self.assertEqual(log._entries, [])


class TwoStageTests(unittest.TestCase):
    def test_both_stages_log_and_second_stage_fires_when_encounter_has_no_reply(self):
        events = InMemoryEventRepository(
            {"eat": _command(result_pool=(StateChange(field="money", delta=-1),)), "fish": _encounter()}
        )
        log = InMemoryEventLogStore()
        play_turn = make_play_turn(events, log=log)
        agent = make_agent(money=10, location_id="jiuguan", location_type="酒楼")
        world = make_tavern_world()

        result = play_turn.handle_player_text(agent, world, "吃饭")

        self.assertEqual(result.command_event_id, "eat")
        self.assertEqual(result.encounter_event_id, "fish")
        self.assertEqual(len(log._entries), 2)  # 命令段与奇遇段各写一条
        self.assertTrue(agent.inventory.has("gold"))
        self.assertEqual(agent.state.name, "idle")

    def test_needs_reply_encounter_parks_and_does_not_run_result_pool_yet(self):
        reply = ReplyOption(aliases=("买下来",), results=(ItemDrop("gold", 1),))
        events = InMemoryEventRepository({"eat": _command(), "fish": _encounter(needs_reply_options=(reply,))})
        play_turn = make_play_turn(events)
        agent = make_agent(money=10, location_id="jiuguan", location_type="酒楼")
        world = make_tavern_world()

        result = play_turn.handle_player_text(agent, world, "吃饭")

        self.assertEqual(result.prompt_event_id, "fish")
        self.assertEqual(agent.pending_encounter_id, "fish")
        self.assertEqual(agent.state.name, "encounter_pending")
        self.assertFalse(agent.inventory.has("gold"))  # 只叙述、不结算


class PendingResolutionTests(unittest.TestCase):
    def _agent_with_pending_fish(self):
        agent = make_agent(money=10, location_id="jiuguan", location_type="酒楼")
        agent.pending_encounter_id = "fish"
        agent.state = EncounterPendingState()
        return agent

    def test_local_option_resolves_via_reply_options_not_global_alias(self):
        reply = ReplyOption(aliases=("买下来",), results=(ItemDrop("gold", 1),))
        events = InMemoryEventRepository({"fish": _encounter(needs_reply_options=(reply,))})
        play_turn = make_play_turn(events)
        agent = self._agent_with_pending_fish()
        world = make_tavern_world()

        result = play_turn.handle_player_text(agent, world, "买下来")

        self.assertTrue(agent.inventory.has("gold"))
        self.assertIsNone(agent.pending_encounter_id)
        self.assertEqual(agent.state.name, "idle")
        self.assertIsNone(result.parse_error)

    def test_unrelated_text_abandons_pending_without_dangling_id(self):
        reply = ReplyOption(aliases=("买下来",), results=(ItemDrop("gold", 1),))
        events = InMemoryEventRepository({"fish": _encounter(needs_reply_options=(reply,))})
        play_turn = make_play_turn(events)
        agent = self._agent_with_pending_fish()
        world = make_tavern_world()

        result = play_turn.handle_player_text(agent, world, "今天天气真好")

        # "算了"/无关话都不命中局部选项 -> 回落全局命令 -> 也解析失败 -> 挂起项按错过清空
        self.assertIsNone(agent.pending_encounter_id)
        self.assertFalse(agent.inventory.has("gold"))
        self.assertEqual(result.parse_error, "听不懂，再说一次？")


class ArbitrationIntegrationTests(unittest.TestCase):
    def test_dead_agent_discards_everything(self):
        events = InMemoryEventRepository({"eat": _command()})
        play_turn = make_play_turn(events)
        agent = make_agent(state=DeadState())
        world = make_tavern_world()
        occ = GameEventOccurrence("eat", TriggerSource.PLAYER, agent.agent_id, make_time(), 0)

        result = play_turn.execute_occurrence(agent, world, occ, events.get_by_id("eat"))

        self.assertIsNone(result)
        self.assertEqual(agent.state.name, "dead")

    def test_closed_door_discards_non_force(self):
        events = InMemoryEventRepository({"eat": _command()})
        play_turn = make_play_turn(events)
        agent = make_agent(state=ClosedDoorState())
        world = make_tavern_world()
        occ = GameEventOccurrence("eat", TriggerSource.SCHEDULE, agent.agent_id, make_time(), 0)

        result = play_turn.execute_occurrence(agent, world, occ, events.get_by_id("eat"))

        self.assertIsNone(result)
        self.assertEqual(agent.state.name, "closed_door")

    def test_acting_encounter_enqueues_and_does_not_run_result_pool(self):
        events = InMemoryEventRepository({"fish": _encounter()})
        play_turn = make_play_turn(events)
        agent = make_agent(state=ActingState())
        world = make_tavern_world()
        occ = GameEventOccurrence("fish", TriggerSource.ENCOUNTER, agent.agent_id, make_time(), 0)

        result = play_turn.execute_occurrence(agent, world, occ, events.get_by_id("fish"))

        self.assertIsNone(result)
        self.assertEqual(agent.pending_encounter_id, "fish")
        self.assertFalse(agent.inventory.has("gold"))  # ENQUEUE 不执行结果池

    def test_second_enqueue_is_dropped_not_queued(self):
        events = InMemoryEventRepository({"fish": _encounter(), "fish2": _encounter(event_id="fish2")})
        play_turn = make_play_turn(events)
        agent = make_agent(state=ActingState())
        world = make_tavern_world()
        play_turn.execute_occurrence(agent, world, GameEventOccurrence("fish", TriggerSource.ENCOUNTER, agent.agent_id, make_time(), 0), events.get_by_id("fish"))
        play_turn.execute_occurrence(agent, world, GameEventOccurrence("fish2", TriggerSource.ENCOUNTER, agent.agent_id, make_time(), 0), events.get_by_id("fish2"))
        self.assertEqual(agent.pending_encounter_id, "fish")  # 不被 fish2 覆盖，不排队堆积


class _FakeNarrativeWriter:
    def __init__(self, text="你捡到了一枚铜钱。") -> None:
        self.text = text
        self.calls = 0

    def complete(self, prompt):
        self.calls += 1
        return self.text


class LiveVariantSupplementationTests(unittest.TestCase):
    """事件命中但 variants 留空——不该崩（IndexError），也不该每次都现场编：
    第一次调 LlmEventWriter（或没配置时用占位文案）补一句并存回仓库，之后同一个
    事件命中直接用存好的那句，不再重复调用。"""

    def test_empty_variants_command_event_gets_fallback_text_without_narrative_writer(self):
        blank = replace(_command(), variants=())
        events = InMemoryEventRepository({"eat": blank})
        play_turn = make_play_turn(events)
        agent = make_agent(money=10)
        world = make_tavern_world()

        result = play_turn.handle_player_text(agent, world, "吃饭")

        self.assertEqual(result.command_event_id, "eat")
        # 没崩，且事件已经被补上了变体、存回了仓库
        self.assertTrue(events.get_by_id("eat").variants)
        self.assertIn("eat", events.get_by_id("eat").variants[0].text)

    def test_empty_variants_command_event_uses_narrative_writer_when_configured(self):
        blank = replace(_command(), variants=())
        events = InMemoryEventRepository({"eat": blank})
        writer = _FakeNarrativeWriter(text="你狼吞虎咽地吃完了一碗面。")
        play_turn = make_play_turn(events, narrative_writer=writer)
        agent = make_agent(money=10)
        world = make_tavern_world()

        play_turn.handle_player_text(agent, world, "吃饭")

        self.assertEqual(events.get_by_id("eat").variants[0].text, "你狼吞虎咽地吃完了一碗面。")
        self.assertEqual(writer.calls, 1)

    def test_generated_variant_is_reused_not_regenerated_on_next_trigger(self):
        blank = replace(_command(), variants=(), cooldown_shichen=0)
        events = InMemoryEventRepository({"eat": blank})
        writer = _FakeNarrativeWriter()
        play_turn = make_play_turn(events, narrative_writer=writer)
        agent = make_agent(money=10)
        world = make_tavern_world()

        play_turn.handle_player_text(agent, world, "吃饭")
        play_turn.handle_player_text(agent, world, "吃饭")

        self.assertEqual(writer.calls, 1)  # 第二次命中直接用存好的文案，不再现场生成

    def test_empty_variants_encounter_event_gets_ensured_before_second_stage(self):
        blank_fish = replace(_encounter(), variants=())
        events = InMemoryEventRepository({"eat": _command(), "fish": blank_fish})
        play_turn = make_play_turn(events)
        agent = make_agent(money=10, location_id="jiuguan", location_type="酒楼")
        world = make_tavern_world()

        result = play_turn.handle_player_text(agent, world, "吃饭")

        self.assertEqual(result.encounter_event_id, "fish")
        self.assertTrue(events.get_by_id("fish").variants)

    def test_existing_non_empty_variants_are_left_untouched(self):
        """已经有文案的事件不该被"顺手"覆盖——narrative_writer 不该被调用。"""
        events = InMemoryEventRepository({"eat": _command()})
        writer = _FakeNarrativeWriter()
        play_turn = make_play_turn(events, narrative_writer=writer)
        agent = make_agent(money=10)
        world = make_tavern_world()

        play_turn.handle_player_text(agent, world, "吃饭")

        self.assertEqual(writer.calls, 0)
        self.assertEqual(events.get_by_id("eat").variants[0].text, "你吃了饭。")


class ChainDeliveryOrderTests(unittest.TestCase):
    def test_chain_event_only_published_after_apply(self):
        from model.domain.results import ChainEvent

        events = InMemoryEventRepository(
            {
                "eat": _command(result_pool=(ChainEvent(event_id="aftermath"),)),
                "aftermath": _encounter(event_id="aftermath"),
            }
        )
        published = []
        play_turn = make_play_turn(events)
        play_turn.bus.subscribe(GameEventOccurrence, lambda occ: published.append(occ.event_id))
        agent = make_agent(money=10)
        world = make_tavern_world()

        play_turn.handle_player_text(agent, world, "吃饭")

        self.assertIn("aftermath", published)


if __name__ == "__main__":
    unittest.main()
