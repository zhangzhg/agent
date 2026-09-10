import unittest
from dataclasses import replace

from model.domain.events import EventVariant, GameEventDef, GameEventOccurrence, ReplyOption, TriggerSource
from model.domain.predicates import Predicate, PredicateGroup, PredicateType
from model.domain.results import ItemDrop, StateChange
from model.domain.states import ActingState, ClosedDoorState, DeadState, EncounterPendingState
from model.repositories.event_log import InMemoryEventLogStore
from model.repositories.sqlite_event_repository import InMemoryEventRepository
from model.services.arbiter import ArbitrationDecision
from model.services.play_turn import _looks_like_gibberish
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


class _FixedEmbeddingPort:
    def __init__(self, vector):
        self._vector = vector

    def embed(self, text):
        return list(self._vector)


class _FakeLiveClient:
    """LiveContentAuthor 用的假 LlmClient——固定返回一段 JSON 文本，不管 prompt
    具体是什么（这些测试关心的是接线是否正确，不是 prompt 内容）。author_location
    走 complete_with_tools()（真正的 function calling，见 llm_tool_loop.py），这里
    直接给最终答案、不模拟工具调用——工具调用本身的round-trip 在
    test_live_content_author.py 里单独测过。"""

    def __init__(self, response: str):
        self.response = response
        self.calls = 0

    def complete(self, prompt):
        self.calls += 1
        return self.response

    def complete_with_tools(self, messages, tools):
        self.calls += 1
        return {"content": self.response}


class _SequencedFakeLiveClient:
    """跟 _FakeLiveClient 不同的是每次调用按顺序弹出下一个预设回复——用于测试
    追问补全这种"同一个 LiveContentAuthor 方法被连续调用好几轮，每轮回复不同"
    的场景。"""

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.calls = 0

    def complete(self, prompt):
        self.calls += 1
        return self._responses.pop(0)

    def complete_with_tools(self, messages, tools):
        self.calls += 1
        return {"content": self._responses.pop(0)}


class CommandIntentFallbackTests(unittest.TestCase):
    """chat_parser 精确匹配失败后，向量兜底 -> 实时创作，依次尝试。"""

    def test_vector_fallback_matches_existing_command_by_semantic_similarity(self):
        eat = replace(_command(), narrative_embedding=(1.0, 0.0))
        events = InMemoryEventRepository({"eat": eat})
        play_turn = make_play_turn(events, embedding=_FixedEmbeddingPort((1.0, 0.0)))
        agent = make_agent(money=10)
        world = make_tavern_world()

        result = play_turn.handle_player_text(agent, world, "我想吃点东西")

        self.assertEqual(result.command_event_id, "eat")

    def test_vector_fallback_computes_and_caches_embedding_for_seeded_events(self):
        """回归测试：content/events/*.py 里内置命令走 seed_all() 直接
        save_event_def() 落库，从来没经过 admin_controller.py::save_event 那条
        计算 narrative_embedding 的路径——曾经因此天生没有 narrative_embedding，
        向量兜底对着"吃饭"这种游戏自带命令永远匹配不上，"吃点东西"只会一直
        "听不懂"。现在应该在第一次用到时现算一次并存回仓库，之后同一个事件
        命中不用再重新算（跟 _ensure_variants 一样的套路）。"""
        eat = _command()  # narrative_embedding 默认是空的，模拟内置命令的真实状态
        self.assertEqual(eat.narrative_embedding, ())
        events = InMemoryEventRepository({"eat": eat})
        embedding = _FixedEmbeddingPort((1.0, 0.0))
        play_turn = make_play_turn(events, embedding=embedding)
        agent = make_agent(money=10)
        world = make_tavern_world()

        result = play_turn.handle_player_text(agent, world, "我想吃点东西")

        self.assertEqual(result.command_event_id, "eat")
        self.assertEqual(events.get_by_id("eat").narrative_embedding, (1.0, 0.0))

    def test_no_embedding_and_no_narrative_writer_still_falls_back_to_parse_failed(self):
        events = InMemoryEventRepository({"eat": _command()})
        play_turn = make_play_turn(events)
        agent = make_agent(money=10)
        world = make_tavern_world()

        result = play_turn.handle_player_text(agent, world, "今天天气怎么样")

        self.assertIsNotNone(result.parse_error)

    def test_live_author_creates_and_immediately_executes_new_command_when_configured(self):
        """规则解析 + 向量兜底都没命中，配置了 narrative_writer 时最后一层实时
        创作——生成的事件立即落库（is_draft=False）并当场执行。"""
        response = (
            '[{"tags": ["生活"], "aliases": [], "variants": ["你即兴弹了一曲，'
            '琴声悠扬。"], "weight": 1.0, "duration_shichen": 1, "cooldown_shichen": 0, '
            '"priority": 5, "result_pool": [], "item_query": ""}]'
        )
        client = _FakeLiveClient(response)
        events = InMemoryEventRepository({})
        play_turn = make_play_turn(events, narrative_writer=client)
        agent = make_agent(money=10)
        world = make_tavern_world()

        result = play_turn.handle_player_text(agent, world, "我想弹会儿琴")

        self.assertIsNotNone(result.command_event_id)
        self.assertTrue(result.command_event_id.startswith("live_"))
        saved = events.get_by_id(result.command_event_id)
        self.assertIsNotNone(saved)
        self.assertFalse(saved.is_draft)
        self.assertTrue(saved.is_command)
        self.assertEqual(saved.variants[0].text, "你即兴弹了一曲，琴声悠扬。")
        # 实时创作没有专门的描述字段——拿第一条变体文案顶上，事件管理列表里
        # 才不会只看到一串 live_xxxxxxxx 的 event_id。
        self.assertEqual(saved.description, "你即兴弹了一曲，琴声悠扬。")

    def test_live_author_rejecting_falls_back_to_parse_failed(self):
        client = _FakeLiveClient("不是 JSON")
        events = InMemoryEventRepository({})
        play_turn = make_play_turn(events, narrative_writer=client)
        agent = make_agent(money=10)
        world = make_tavern_world()

        result = play_turn.handle_player_text(agent, world, "asdkjhaskjdh")

        self.assertIsNotNone(result.parse_error)
        self.assertEqual(len(events.load_event_defs(None)), 0)

    def test_pure_gibberish_never_reaches_the_llm(self):
        """现场跑真实 GLM 账号时发现的问题：glm-4-flash 就算 prompt 明确写了
        "说不通就拒绝"，对着纯乱码也会硬编一个场景、甚至扣钱——提示词管不住
        这个模型，改成本地先挡一层："asdkjhaskjdh" 这种一个汉字都没有的输入，
        压根不该走到大模型那一步（不管假 client 会返回什么）。"""
        client = _FakeLiveClient('[{"tags": ["生活"], "aliases": [], "variants": ["瞎编的文案"], '
                                  '"weight": 1.0, "duration_shichen": 1, "cooldown_shichen": 0, '
                                  '"priority": 5, "result_pool": [{"kind": "state_change", "field": "money", "delta": -10}], '
                                  '"item_query": ""}]')
        events = InMemoryEventRepository({})
        play_turn = make_play_turn(events, narrative_writer=client)
        agent = make_agent(money=10)
        world = make_tavern_world()

        result = play_turn.handle_player_text(agent, world, "asdkjhaskjdhaksjdh")

        self.assertIsNotNone(result.parse_error)
        self.assertEqual(client.calls, 0)  # 根本没调大模型
        self.assertEqual(agent.money, 10)  # 没有被瞎扣钱
        self.assertEqual(len(events.load_event_defs(None)), 0)


class LooksLikeGibberishTests(unittest.TestCase):
    def test_pure_ascii_is_gibberish(self):
        self.assertTrue(_looks_like_gibberish("asdkjhaskjdh"))

    def test_contains_chinese_is_not_gibberish(self):
        self.assertFalse(_looks_like_gibberish("我想弹会儿琴"))

    def test_mixed_ascii_and_chinese_is_not_gibberish(self):
        self.assertFalse(_looks_like_gibberish("asdf我想去集市"))

    def test_empty_string_is_gibberish(self):
        self.assertTrue(_looks_like_gibberish(""))


class LiveDestinationAuthoringTests(unittest.TestCase):
    """移动目的地在世界里找不到时的最后一层兜底：实时创作新地点。"""

    def test_internal_destination_creates_child_location_and_moves_there(self):
        response = '{"name": "藏经阁", "kind": "集市", "is_internal": true}'
        client = _FakeLiveClient(response)
        events = InMemoryEventRepository({})
        play_turn = make_play_turn(events, narrative_writer=client)
        agent = make_agent(money=10, location_id="city", location_type="城市")
        world = make_tavern_world()

        result = play_turn.handle_player_text(agent, world, "我想去藏经阁")

        self.assertIsNone(result.reject_reason)
        new_loc = next(loc for loc in world.mutable_state().locations.values() if loc.name == "藏经阁")
        self.assertEqual(agent.location_id, new_loc.location_id)
        self.assertFalse(new_loc.hidden)
        self.assertTrue(any(
            r.from_id == "city" and r.to_id == new_loc.location_id for r in world.mutable_state().routes
        ))

    def test_external_destination_creates_hidden_location_without_moving(self):
        response = '{"name": "东海仙岛", "kind": "秘境", "is_internal": false}'
        client = _FakeLiveClient(response)
        events = InMemoryEventRepository({})
        play_turn = make_play_turn(events, narrative_writer=client)
        agent = make_agent(money=10, location_id="city", location_type="城市")
        world = make_tavern_world()

        result = play_turn.handle_player_text(agent, world, "我想去东海仙岛")

        self.assertEqual(agent.location_id, "city")  # 没有移动
        self.assertIn("尚未对外开放", result.reject_reason)
        new_loc = next(loc for loc in world.mutable_state().locations.values() if loc.name == "东海仙岛")
        self.assertTrue(new_loc.hidden)
        self.assertFalse(new_loc.discovered)

    def test_model_rejecting_nonsense_falls_back_to_not_found_and_creates_nothing(self):
        client = _FakeLiveClient('{"reject": true}')
        events = InMemoryEventRepository({})
        play_turn = make_play_turn(events, narrative_writer=client)
        agent = make_agent(money=10, location_id="city", location_type="城市")
        world = make_tavern_world()
        before_count = len(world.mutable_state().locations)

        result = play_turn.handle_player_text(agent, world, "我想去阿卡林星")

        self.assertEqual(agent.location_id, "city")
        self.assertEqual(result.reject_reason, "找不到「阿卡林星」这个地方。")
        self.assertEqual(len(world.mutable_state().locations), before_count)


class PendingClarificationTests(unittest.TestCase):
    """LiveContentAuthor 判断信息不全时的追问挂起态——最多真的问出 3 次，
    第 4 次评估时还不够就放弃、清挂起态、回落原有文案。"""

    def test_command_clarification_resolves_after_one_followup(self):
        client = _SequencedFakeLiveClient([
            '{"needs_clarification": true, "question": "你想对谁做这件事？"}',
            '[{"tags": ["生活"], "aliases": [], "variants": ["你教训了那个泼皮。"], '
            '"weight": 1.0, "duration_shichen": 1, "cooldown_shichen": 0, '
            '"priority": 5, "result_pool": [], "item_query": ""}]',
        ])
        events = InMemoryEventRepository({})
        play_turn = make_play_turn(events, narrative_writer=client)
        agent = make_agent(money=10)
        world = make_tavern_world()

        first = play_turn.handle_player_text(agent, world, "教训一下")
        self.assertEqual(first.freeform_narrative, "你想对谁做这件事？")
        self.assertIsNotNone(agent.pending_clarification)
        self.assertEqual(agent.pending_clarification.kind, "command")
        self.assertEqual(agent.pending_clarification.attempts, 1)

        second = play_turn.handle_player_text(agent, world, "那个泼皮")
        self.assertIsNone(agent.pending_clarification)
        self.assertIsNotNone(second.command_event_id)
        self.assertTrue(second.command_event_id.startswith("live_"))
        saved = events.get_by_id(second.command_event_id)
        self.assertEqual(saved.variants[0].text, "你教训了那个泼皮。")

    def test_location_clarification_resolves_after_one_followup(self):
        client = _SequencedFakeLiveClient([
            '{"needs_clarification": true, "question": "你是想找个僻静角落，还是想去别的城市？"}',
            '{"name": "藏经阁", "kind": "集市", "is_internal": true}',
        ])
        events = InMemoryEventRepository({})
        play_turn = make_play_turn(events, narrative_writer=client)
        agent = make_agent(money=10, location_id="city", location_type="城市")
        world = make_tavern_world()

        first = play_turn.handle_player_text(agent, world, "我想去别的地方")
        self.assertEqual(first.freeform_narrative, "你是想找个僻静角落，还是想去别的城市？")
        self.assertEqual(agent.pending_clarification.kind, "location")

        second = play_turn.handle_player_text(agent, world, "找个热闹的地方逛逛")
        self.assertIsNone(agent.pending_clarification)
        new_loc = next(loc for loc in world.mutable_state().locations.values() if loc.name == "藏经阁")
        self.assertEqual(agent.location_id, new_loc.location_id)

    def test_gives_up_after_three_questions_asked(self):
        """连续 4 轮评估都说信息不全——前 3 次应该真的问出来，第 4 次评估时才
        放弃、清挂起态、回落"听不懂"，不会无限问下去。"""
        question = '{"needs_clarification": true, "question": "能说得再具体点吗？"}'
        client = _SequencedFakeLiveClient([question, question, question, question])
        events = InMemoryEventRepository({})
        play_turn = make_play_turn(events, narrative_writer=client)
        agent = make_agent(money=10)
        world = make_tavern_world()

        r1 = play_turn.handle_player_text(agent, world, "做点什么")
        self.assertEqual(r1.freeform_narrative, "能说得再具体点吗？")
        self.assertEqual(agent.pending_clarification.attempts, 1)

        r2 = play_turn.handle_player_text(agent, world, "就做点事")
        self.assertEqual(r2.freeform_narrative, "能说得再具体点吗？")
        self.assertEqual(agent.pending_clarification.attempts, 2)

        r3 = play_turn.handle_player_text(agent, world, "反正就做点事")
        self.assertEqual(r3.freeform_narrative, "能说得再具体点吗？")
        self.assertEqual(agent.pending_clarification.attempts, 3)

        r4 = play_turn.handle_player_text(agent, world, "还是做点事")
        self.assertIsNone(agent.pending_clarification)  # 放弃了，挂起态清掉
        self.assertIsNotNone(r4.parse_error)  # 回落原有"听不懂"文案
        self.assertEqual(client.calls, 4)
        self.assertEqual(len(events.load_event_defs(None)), 0)  # 没有落库任何半成品


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
