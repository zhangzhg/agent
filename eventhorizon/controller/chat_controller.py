"""controller/chat_controller.py — 薄入口（对应 README §7 / GAME_DESIGN §3.1）。

薄：parse 失败回文，否则转给 play_turn.handle_player_text。不调用 arbiter /
pipeline / matching——那些全部封在已经装配好的 PlayTurnService 里（见
bootstrap.py 的组合根）。

只读查询命令（inspect_npc 等，GAME_DESIGN §3.1）在这里被拦下，直接调只读服务，
不进 PlayTurnService——它们不改状态、不消耗回合、不该有 AppliedDiff。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from model.services.chat_parser import INSPECT_NPC_EVENT_ID, QUERY_EVENT_IDS
from view.narrative_renderer import placeholders_from, render_turn
from view.npc_info_card_view import render_npc_info_card
from view.schemas.chat_schemas import ChatRequest, ChatResponse
from view.state_diff_view import StateDiffView

if TYPE_CHECKING:
    from model.services.play_turn import PlayTurnService
    from model.services.ports import AgentRepository, EventRepository, WorldRepository


class ChatController:
    def __init__(
        self,
        agent_repo: "AgentRepository",
        world_repo: "WorldRepository",
        play_turn: "PlayTurnService",
        events: "EventRepository",
    ) -> None:
        self._agent_repo = agent_repo
        self._world_repo = world_repo
        self._play_turn = play_turn
        self._events = events

    def on_player_message(self, raw_text: str, agent_id: str) -> ChatResponse:
        agent = self._agent_repo.load(agent_id)
        world = self._world_repo.assemble_view()

        # 只读查询命令不进两段式循环：不改状态、不消耗回合、不进 AgentEventHistory。
        cmd = self._play_turn.parser.parse(raw_text, agent.scene_focus)
        if cmd is not None and (cmd.is_query or cmd.event_id in QUERY_EVENT_IDS):
            return self._handle_query(cmd, agent)

        result = self._play_turn.handle_player_text(agent, world, raw_text)
        self._agent_repo.save(agent)
        self._world_repo.save(agent.time_anchor.current_game_time)

        event_index = {
            event_id: self._events.get_by_id(event_id)
            for event_id in (result.command_event_id, result.encounter_event_id, result.prompt_event_id)
            if event_id is not None
        }
        narrative = render_turn(result, event_index, placeholders_from(agent), location_condition=world.condition_of(agent.location_id))
        diff_lines = StateDiffView.from_applied_diff(result.command_diff).to_summary_lines()
        diff_lines += StateDiffView.from_applied_diff(result.encounter_diff).to_summary_lines()
        return ChatResponse(
            narrative=narrative,
            state_diff_lines=diff_lines,
            agent_state=agent.state.name,
            parse_error=result.parse_error,
            reject_reason=result.reject_reason,
        )

    def _handle_query(self, cmd, agent) -> ChatResponse:
        if cmd.event_id == INSPECT_NPC_EVENT_ID:
            return self._handle_inspect_npc(cmd, agent)
        return ChatResponse(narrative="（这项查询暂未开放。）", agent_state=agent.state.name)

    def _handle_inspect_npc(self, cmd, agent) -> ChatResponse:
        if not cmd.target:
            return ChatResponse(narrative="打听谁？", agent_state=agent.state.name)
        try:
            npc = self._agent_repo.load(cmd.target)
        except LookupError:
            return ChatResponse(narrative=f"没听说过「{cmd.target}」这号人物。", agent_state=agent.state.name)

        from model.services.npc_query_service import build_npc_info_card

        card = build_npc_info_card(npc, agent, biography=None, now=agent.time_anchor.current_game_time)
        return ChatResponse(narrative=render_npc_info_card(card), agent_state=agent.state.name)

    # 保留与文档同名的函数式入口，行为等价，方便直接照 README §7 的示例调用。
    def __call__(self, raw_text: str, agent_id: str) -> ChatResponse:
        return self.on_player_message(raw_text, agent_id)


def build_request(agent_id: str, text: str) -> ChatRequest:
    return ChatRequest(agent_id=agent_id, text=text)
