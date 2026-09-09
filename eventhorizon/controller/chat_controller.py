"""controller/chat_controller.py — 薄入口（对应 README §7 / GAME_DESIGN §3.1）。

薄：parse 失败回文，否则转给 play_turn.handle_player_text。不调用 arbiter /
pipeline / matching——那些全部封在已经装配好的 PlayTurnService 里（见
bootstrap.py 的组合根）。

只读查询命令（inspect_npc 等，GAME_DESIGN §3.1）在这里被拦下，直接调只读服务，
不进 PlayTurnService——它们不改状态、不消耗回合、不该有 AppliedDiff。
"""
from __future__ import annotations

import random
from typing import TYPE_CHECKING

from model.services.chat_parser import INSPECT_NPC_EVENT_ID, MOVE_EVENT_ID, QUERY_EVENT_IDS, SCAN_EVENT_ID
from model.services.play_turn import default_move_def
from view.narrative_renderer import placeholders_from, render_turn
from view.npc_info_card_view import render_npc_info_card
from view.schemas.chat_schemas import ChatRequest, ChatResponse
from view.state_diff_view import StateDiffView

if TYPE_CHECKING:
    from model.domain.events import GameEventDef
    from model.domain.map import WorldView
    from model.services.play_turn import PlayTurnService
    from model.services.ports import AgentRepository, EventRepository, WorldRepository


class ChatController:
    def __init__(
        self,
        agent_repo: "AgentRepository",
        world_repo: "WorldRepository",
        play_turn: "PlayTurnService",
        events: "EventRepository",
        rng: "random.Random | None" = None,
    ) -> None:
        self._agent_repo = agent_repo
        self._world_repo = world_repo
        self._play_turn = play_turn
        self._events = events
        self._rng = rng or random.Random()  # 神识扫描（_handle_scan）用；与对局的 rng 无需同一份

    def on_player_message(self, raw_text: str, agent_id: str) -> ChatResponse:
        agent = self._agent_repo.load(agent_id)
        world = self._world_repo.assemble_view()

        # 只读查询命令不进两段式循环：不改状态、不消耗回合、不进 AgentEventHistory。
        cmd = self._play_turn.parser.parse(raw_text, agent.scene_focus)
        if cmd is not None and (cmd.is_query or cmd.event_id in QUERY_EVENT_IDS):
            return self._handle_query(cmd, agent, world)

        result = self._play_turn.handle_player_text(agent, world, raw_text)
        self._agent_repo.save(agent)
        self._world_repo.save(agent.time_anchor.current_game_time)

        event_index = {
            event_id: self._events.get_by_id(event_id) or self._move_fallback(event_id)
            for event_id in (result.command_event_id, result.encounter_event_id, result.prompt_event_id)
            if event_id is not None
        }
        narrative = render_turn(result, event_index, placeholders_from(agent, world), location_condition=world.condition_of(agent.location_id))
        diff_lines = StateDiffView.from_applied_diff(result.command_diff).to_summary_lines()
        diff_lines += StateDiffView.from_applied_diff(result.encounter_diff).to_summary_lines()
        return ChatResponse(
            narrative=narrative,
            state_diff_lines=diff_lines,
            agent_state=agent.state.name,
            parse_error=result.parse_error,
            reject_reason=result.reject_reason,
        )

    @staticmethod
    def _move_fallback(event_id: str) -> "GameEventDef | None":
        """event_id="move" 在事件仓库里查不到是正常情况——除非内容作者专门录入过
        一条同名事件，PlayTurnService._handle_move 用的都是它现算的兜底定义（见
        model/services/play_turn.py::default_move_def），不是仓库里的记录。这里
        补一次同样的兜底查询，否则渲染时找不到对应的 GameEventDef、"你来到了
        {地点}。"这句确认文案会被 render_turn 悄悄跳过——纯移动会显示成"无事
        发生"，带了第二段奇遇的移动则看起来像"平白无故撞上一个事件"，两种都会
        让玩家看不懂到底发生了什么（真正的 bug 报告来源）。"""
        if event_id != MOVE_EVENT_ID:
            return None
        return default_move_def()

    def _handle_query(self, cmd, agent, world: "WorldView") -> ChatResponse:
        if cmd.event_id == INSPECT_NPC_EVENT_ID:
            return self._handle_inspect_npc(cmd, agent)
        if cmd.event_id == SCAN_EVENT_ID:
            return self._handle_scan(agent, world)
        return ChatResponse(narrative="（这项查询暂未开放。）", agent_state=agent.state.name)

    def _handle_scan(self, agent, world: "WorldView") -> ChatResponse:
        from model.services.exploration_service import scan_for_hidden_locations

        result = scan_for_hidden_locations(agent.location_id, world, self._rng)
        if result.found_location_id is not None:
            # 命中会改世界状态（discovered 翻真），落盘规则跟主流程一致：改了世界就存世界。
            self._world_repo.save(agent.time_anchor.current_game_time)
        return ChatResponse(narrative=result.narrative, agent_state=agent.state.name)

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
