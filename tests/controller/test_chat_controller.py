import unittest
from unittest.mock import MagicMock

from controller.chat_controller import ChatController
from model.domain.map import Location, LocationKind, WorldState, WorldView
from model.services.chat_parser import ParsedCommand
from model.services.turn_result import TurnResult
from tests.helpers import make_agent, make_world


class _FixedRng:
    """rng 双替身：random() 返回构造时给定的值，choice() 直接取第一个候选——
    scan_for_hidden_locations 只用到这两个方法，不用拉真的 random.Random 进来。"""

    def __init__(self, roll: float) -> None:
        self._roll = roll

    def random(self) -> float:
        return self._roll

    def choice(self, seq):
        return seq[0]


def _non_query_play_turn_mock(event_id: str = "eat") -> MagicMock:
    """ChatController 现在会先用 play_turn.parser 判断是不是只读查询命令
    （GAME_DESIGN §3.1），所以纯 MagicMock() 的 parser.parse() 会返回一个"什么都
    真"的 Mock，把每条命令误判成查询。测试用这个 helper 把 parser 配成一条
    普通（非查询）命令。"""
    play_turn = MagicMock()
    play_turn.parser.parse.return_value = ParsedCommand(
        event_id=event_id, location_hint=None, target=None, args={}, is_query=False
    )
    return play_turn


class ChatControllerTests(unittest.TestCase):
    def test_calls_handle_player_text_exactly_once(self):
        agent = make_agent()
        agent_repo = MagicMock()
        agent_repo.load.return_value = agent
        world_repo = MagicMock()
        world_repo.assemble_view.return_value = make_world()
        play_turn = _non_query_play_turn_mock()
        play_turn.handle_player_text.return_value = TurnResult()
        events = MagicMock()
        events.get_by_id.return_value = None

        controller = ChatController(agent_repo, world_repo, play_turn, events)
        controller.on_player_message("吃饭", "A")

        play_turn.handle_player_text.assert_called_once()
        agent_repo.save.assert_called_once_with(agent)

    def test_response_reports_agent_state_after_turn(self):
        agent = make_agent()
        agent_repo = MagicMock()
        agent_repo.load.return_value = agent
        world_repo = MagicMock()
        world_repo.assemble_view.return_value = make_world()
        play_turn = _non_query_play_turn_mock("breakthrough")
        play_turn.handle_player_text.return_value = TurnResult(reject_reason="条件未满足。")
        events = MagicMock()
        events.get_by_id.return_value = None

        controller = ChatController(agent_repo, world_repo, play_turn, events)
        response = controller.on_player_message("突破", "A")

        self.assertEqual(response.reject_reason, "条件未满足。")
        self.assertEqual(response.agent_state, "idle")

    def test_move_confirmation_narrative_shows_even_without_persisted_move_event(self):
        """move 命令没有对应的库内 GameEventDef——PlayTurnService._handle_move 用
        的是现算的兜底定义（model/services/play_turn.py::default_move_def），events
        仓库查 event_id="move" 天然查不到。回归测试：曾经因为 chat_controller.py
        只按仓库查找渲染用的事件定义，导致"你来到了{地点}。"这句确认文案被
        render_turn 悄悄跳过——纯移动显示成"无事发生"，带了第二段奇遇的移动又
        看起来像凭空冒出一个不相关的事件，两种都会让玩家看不懂到底发生了什么。"""
        from model.services.chat_parser import MOVE_EVENT_ID
        from model.services.play_turn import default_move_def

        agent = make_agent(location_id="cangwu_gate")
        agent_repo = MagicMock()
        agent_repo.load.return_value = agent
        state = WorldState(locations={"cangwu_gate": Location("cangwu_gate", "苍梧城·城门", LocationKind.CITY, "城门")})
        world_repo = MagicMock()
        world_repo.assemble_view.return_value = WorldView(_state=state)
        play_turn = _non_query_play_turn_mock(MOVE_EVENT_ID)
        play_turn.handle_player_text.return_value = TurnResult(command_event_id=MOVE_EVENT_ID, command_variant=0)
        events = MagicMock()
        events.get_by_id.return_value = None  # 仓库里没有 event_id="move" 这条记录

        controller = ChatController(agent_repo, world_repo, play_turn, events)
        response = controller.on_player_message("去城门", "A")

        self.assertIn(default_move_def().variants[0].text.format(地点="苍梧城·城门"), response.narrative)

    def test_query_command_bypasses_play_turn_entirely(self):
        """打听 NPC 是只读查询：不该碰 PlayTurnService（GAME_DESIGN §3.1）。"""
        agent = make_agent()
        agent_repo = MagicMock()
        agent_repo.load.side_effect = [agent, LookupError()]
        world_repo = MagicMock()
        play_turn = MagicMock()
        play_turn.parser.parse.return_value = ParsedCommand(
            event_id="inspect_npc", location_hint=None, target="王麻子", args={}, is_query=True
        )
        events = MagicMock()

        controller = ChatController(agent_repo, world_repo, play_turn, events)
        response = controller.on_player_message("打听王麻子", "A")

        play_turn.handle_player_text.assert_not_called()
        self.assertIn("王麻子", response.narrative)

    def test_scan_command_discovers_hidden_location_and_saves_world(self):
        """神识扫描命中：不进 PlayTurnService，命中后把发现状态存回 world_repo
        （GAME_DESIGN §5.3：discovered 要跨会话保留）。"""
        agent = make_agent(location_id="cangwu")
        agent_repo = MagicMock()
        agent_repo.load.return_value = agent
        state = WorldState(locations={
            "cangwu": Location("cangwu", "苍梧城", LocationKind.CITY, "城市"),
            "guixu": Location(
                "guixu", "归墟秘境", LocationKind.SECRET_REALM, "秘境",
                parent_location_id="cangwu", hidden=True, concealment=0.9,
            ),
        })
        world_repo = MagicMock()
        world_repo.assemble_view.return_value = WorldView(_state=state)
        play_turn = MagicMock()
        play_turn.parser.parse.return_value = ParsedCommand(
            event_id="scan", location_hint=None, target=None, args={}, is_query=True
        )
        events = MagicMock()

        controller = ChatController(agent_repo, world_repo, play_turn, events, rng=_FixedRng(0.0))
        response = controller.on_player_message("神识扫描", "A")

        play_turn.handle_player_text.assert_not_called()
        self.assertIn("归墟秘境", response.narrative)
        self.assertTrue(state.get("guixu").discovered)
        world_repo.save.assert_called_once()

    def test_scan_command_miss_does_not_save_world(self):
        """没扫到就不该多写一次盘——世界状态压根没变。"""
        agent = make_agent(location_id="cangwu")
        agent_repo = MagicMock()
        agent_repo.load.return_value = agent
        state = WorldState(locations={"cangwu": Location("cangwu", "苍梧城", LocationKind.CITY, "城市")})
        world_repo = MagicMock()
        world_repo.assemble_view.return_value = WorldView(_state=state)
        play_turn = MagicMock()
        play_turn.parser.parse.return_value = ParsedCommand(
            event_id="scan", location_hint=None, target=None, args={}, is_query=True
        )
        events = MagicMock()

        controller = ChatController(agent_repo, world_repo, play_turn, events, rng=_FixedRng(1.0))
        response = controller.on_player_message("神识扫描", "A")

        self.assertTrue(response.narrative)
        world_repo.save.assert_not_called()


class WorldQueryAssistantWiringTests(unittest.TestCase):
    """"我在哪里"这类世界信息问答：命中关键词粗筛后交给 WorldQueryAssistant，
    答上来就直接回文案、不进两段式循环；助手判断"这其实不是在问信息"（返回
    None）就原样回落到正常的命令解析流程，不能截胡一句正常的游戏指令。"""

    def test_info_question_answered_by_assistant_bypasses_play_turn(self):
        agent = make_agent()
        agent_repo = MagicMock()
        agent_repo.load.return_value = agent
        world_repo = MagicMock()
        world_repo.assemble_view.return_value = make_world()
        play_turn = _non_query_play_turn_mock()
        events = MagicMock()
        world_query = MagicMock()
        world_query.answer.return_value = "你现在在某城。"

        controller = ChatController(agent_repo, world_repo, play_turn, events, world_query=world_query)
        response = controller.on_player_message("我在哪里", "A")

        world_query.answer.assert_called_once_with(agent, world_repo.assemble_view.return_value, "我在哪里")
        play_turn.handle_player_text.assert_not_called()
        self.assertEqual(response.narrative, "你现在在某城。")

    def test_assistant_declining_falls_back_to_normal_pipeline(self):
        agent = make_agent()
        agent_repo = MagicMock()
        agent_repo.load.return_value = agent
        world_repo = MagicMock()
        world_repo.assemble_view.return_value = make_world()
        play_turn = _non_query_play_turn_mock()
        play_turn.handle_player_text.return_value = TurnResult()
        events = MagicMock()
        events.get_by_id.return_value = None
        world_query = MagicMock()
        world_query.answer.return_value = None  # 判断下来不是信息问答／没答上来

        controller = ChatController(agent_repo, world_repo, play_turn, events, world_query=world_query)
        controller.on_player_message("我在哪里能买到好装备", "A")

        play_turn.handle_player_text.assert_called_once()

    def test_no_world_query_configured_skips_straight_to_normal_pipeline(self):
        """没配大模型时 world_query 是 None——关键词命中也不该报错，直接走原流程。"""
        agent = make_agent()
        agent_repo = MagicMock()
        agent_repo.load.return_value = agent
        world_repo = MagicMock()
        world_repo.assemble_view.return_value = make_world()
        play_turn = _non_query_play_turn_mock()
        play_turn.handle_player_text.return_value = TurnResult()
        events = MagicMock()
        events.get_by_id.return_value = None

        controller = ChatController(agent_repo, world_repo, play_turn, events, world_query=None)
        controller.on_player_message("我在哪里", "A")

        play_turn.handle_player_text.assert_called_once()

    def test_non_info_text_never_reaches_the_assistant(self):
        """关键词粗筛没命中——压根不该调用助手（省一次没必要的大模型请求）。"""
        agent = make_agent()
        agent_repo = MagicMock()
        agent_repo.load.return_value = agent
        world_repo = MagicMock()
        world_repo.assemble_view.return_value = make_world()
        play_turn = _non_query_play_turn_mock()
        play_turn.handle_player_text.return_value = TurnResult()
        events = MagicMock()
        events.get_by_id.return_value = None
        world_query = MagicMock()

        controller = ChatController(agent_repo, world_repo, play_turn, events, world_query=world_query)
        controller.on_player_message("吃饭", "A")

        world_query.answer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
