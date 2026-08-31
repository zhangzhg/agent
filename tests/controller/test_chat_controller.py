import unittest
from unittest.mock import MagicMock

from controller.chat_controller import ChatController
from model.services.chat_parser import ParsedCommand
from model.services.turn_result import TurnResult
from tests.helpers import make_agent, make_world


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


if __name__ == "__main__":
    unittest.main()
