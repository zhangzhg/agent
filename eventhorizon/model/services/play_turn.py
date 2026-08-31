"""model/services/play_turn.py — 对局两段循环（唯一编排处，对应 README 2.2 / 4.9）。

对局唯一入口：玩家聊天、NPC 日程、时钟到点，都 EventBus.publish 一条已解析好的
GameEventOccurrence（或先 publish 命令意图，由本服务订阅后补全）。顺序：仲裁 →
谓词校验 → 状态机 → 责任链产出 diff → 一次性 apply → 记日志 → 再决定是否抽第二段。

状态类不持有 EventBus；本服务在转换成功后 publish(AgentStateChanged)。
服务对象一律无跨回合状态——挂起态（pending_encounter_id / pending_scenario）全部
存在 Agent 上，PlayTurnService 自身不缓存任何跨轮次数据。
"""
from __future__ import annotations

import random
from dataclasses import replace
from typing import TYPE_CHECKING

from model.domain.diff import AppliedDiff, apply_agent_diff
from model.domain.events import GameEventOccurrence, TriggerSource
from model.domain.results import StateChange
from model.domain.system_events import AgentStateChanged
from model.services.arbiter import ArbitrationDecision, EventArbiter
from model.services.chat_parser import MOVE_EVENT_ID, QUERY_EVENT_IDS, RETREAT_START_EVENT_ID
from model.services.matching import MatchContext, coarse_filter, pick_variant, reweight_and_pick, tidal_beast_weight_multiplier
from model.services.pipeline import Pipeline, PipelineContext
from model.services.retreat_intent_parser import parse_retreat_duration, stop_when_realm_reached
from model.services.turn_result import TurnResult

if TYPE_CHECKING:
    from model.domain.agent import Agent
    from model.domain.balance import BalanceTable
    from model.domain.events import GameEventDef
    from model.domain.map import WorldView
    from model.services.chat_parser import ChatParser
    from model.services.clock_service import GameClock, RetreatService
    from model.services.event_bus import EventBus
    from model.services.ports import EventLogStore, EventRepository, ScenarioRepository

_RETREAT_PROMPT_TEXT = '要闭关多久？（可以说"十年""到金丹为止"或"随便"）'
_RETREAT_UNPARSEABLE_TEXT = '没听懂要闭关多久，你可以说"十年""到金丹为止"或"随便"。'


class PlayTurnService:
    def __init__(
        self,
        bus: "EventBus",
        arbiter: EventArbiter,
        pipeline: Pipeline,
        parser: "ChatParser",
        events: "EventRepository",
        scenarios: "ScenarioRepository",
        rng: random.Random,
        log: "EventLogStore | None",
        clock: "GameClock",
        retreat: "RetreatService | None" = None,
        balance: "BalanceTable | None" = None,
    ) -> None:
        self.bus = bus
        self.arbiter = arbiter
        self.pipeline = pipeline
        self.parser = parser
        self.events = events
        self.scenarios = scenarios
        self.rng = rng
        self.log = log
        self.clock = clock
        self.retreat = retreat
        self.balance = balance
        self.bus.subscribe(GameEventOccurrence, self._on_occurrence_published)

    # ---------- 总线订阅：日程/连锁等通过 publish 投递的 Occurrence 走这里 ----------
    def _on_occurrence_published(self, occ: GameEventOccurrence) -> None:
        defn = self.events.get_by_id(occ.event_id)
        if defn is None or defn.is_draft:
            return
        # 世界引用由调用方在 publish 前已经通过闭包/上下文绑定；总线路径下 world 由
        # 订阅时注入的 world_provider 提供，MVP 单主角场景通常已知晓当前 WorldView。
        world = self._world_provider() if self._world_provider else None
        agent = self._agent_for(occ.agent_id)
        if agent is None or world is None:
            return
        self.execute_occurrence(agent, world, occ, defn)

    _world_provider = None
    _agent_lookup = None

    def bind_context(self, world_provider, agent_lookup) -> None:
        """把"总线路径怎么找到 World/Agent"的胶水显式接进来（controller/clock 层持有
        真正的仓库引用，PlayTurnService 本身不缓存跨回合状态）。"""
        self._world_provider = world_provider
        self._agent_lookup = agent_lookup

    def _agent_for(self, agent_id: str) -> "Agent | None":
        return self._agent_lookup(agent_id) if self._agent_lookup else None

    # ---------- 入口：一次玩家输入 ----------
    def handle_player_text(self, agent: "Agent", world: "WorldView", raw: str) -> TurnResult:
        # 每轮输入都计数（成功/失败都算），驱动"提示只出现在前 3 轮"（GAME_DESIGN §1.1）
        apply_agent_diff(agent, AppliedDiff(attr_deltas=(("turn_count", 1.0),)))

        # 0) 闭关时长追问优先于一切（GAME_DESIGN §4.3）：一句话答不上就一直卡在这
        if agent.pending_retreat_prompt:
            return self._handle_retreat_answer(agent, world, raw)

        # 1) 挂起态优先：先试局部选项，再回落全局命令（见 README 1.11 解析优先级）
        if agent.pending_scenario is not None or agent.pending_encounter_id is not None:
            resolved = self._try_resolve_pending(agent, world, raw)
            if resolved is not None:
                return resolved
            self._abandon_pending(agent)  # 玩家改主意：挂起项按"错过"清掉，经 diff 落库

        # 2) 常规命令
        cmd = self.parser.parse(raw, agent.scene_focus)
        if cmd is None:
            return TurnResult.parse_failed(self._soft_guidance_message(agent, world))
        if cmd.is_query or cmd.event_id in QUERY_EVENT_IDS:
            # 只读查询命令由 controller 直接调只读服务处理，不该走到这里；防御性拒绝。
            return TurnResult.rejected("这个只能查，改变不了什么，换句话说说你想做什么？")
        if cmd.event_id == MOVE_EVENT_ID:
            return self._handle_move(agent, world, cmd)
        if cmd.event_id == RETREAT_START_EVENT_ID:
            return self._handle_retreat_start(agent)

        defn = self.events.get_by_id(cmd.event_id)
        if defn is None or defn.is_draft or not defn.is_command:
            return TurnResult.parse_failed(self._soft_guidance_message(agent, world))
        occ = self._new_occurrence(agent, defn, TriggerSource.PLAYER)
        return self.execute_occurrence(agent, world, occ, defn) or TurnResult.rejected("现在做不了这个。")

    def _soft_guidance_message(self, agent: "Agent", world: "WorldView") -> str:
        """GAME_DESIGN §1.1：前 3 轮给软性引导（从当前地点合格池现取别名举例），
        之后回归简单的"听不懂"，避免变成事实上的教程文本。"""
        if agent.turn_count > 3:
            return "听不懂，再说一次？"
        pool = [e for e in self.events.load_event_defs(agent.location_type) if e.is_command and not e.is_draft]
        examples = self.parser.suggest_aliases(pool, n=2)
        if not examples:
            return "听不懂，再说一次？"
        examples_text = "或".join(f'"{a}"' for a in examples)
        return f"听不懂，要不试试{examples_text}？"

    # ---------- 系统命令：move / retreat_start（GAME_DESIGN §3.1，非库内事件）----------
    def _handle_move(self, agent: "Agent", world: "WorldView", cmd) -> TurnResult:
        if agent.state.name != "idle":
            return TurnResult.rejected("现在走不开。")
        destination = world.find_location_by_name(cmd.location_hint) if cmd.location_hint else None
        if destination is None:
            hint = cmd.location_hint or "那里"
            return TurnResult.rejected(f"找不到「{hint}」这个地方。")
        base = self.events.get_by_id(MOVE_EVENT_ID) or _default_move_def()
        synthetic = replace(
            base, result_pool=(StateChange(field="location", set_to=destination.location_id),), predicate=None, is_command=True
        )
        occ = self._new_occurrence(agent, synthetic, TriggerSource.PLAYER)
        return self.execute_occurrence(agent, world, occ, synthetic) or TurnResult.rejected("现在做不了这个。")

    def _handle_retreat_start(self, agent: "Agent") -> TurnResult:
        if self.retreat is None or self.balance is None:
            return TurnResult.rejected("眼下没法闭关。")
        if agent.state.name != "idle":
            return TurnResult.rejected("现在走不开，没法说走就走地闭关。")
        apply_agent_diff(agent, AppliedDiff(pending_retreat_prompt_set=True))
        return TurnResult(freeform_narrative=_RETREAT_PROMPT_TEXT)

    def _handle_retreat_answer(self, agent: "Agent", world: "WorldView", raw: str) -> TurnResult:
        plan = parse_retreat_duration(raw, agent, self.balance)
        if plan is None:
            return TurnResult.rejected(_RETREAT_UNPARSEABLE_TEXT)
        apply_agent_diff(agent, AppliedDiff(pending_retreat_prompt_set=False))

        before_realm, before_cultivation = agent.realm, agent.cultivation
        stop_when = stop_when_realm_reached(plan.stop_at_realm) if plan.stop_at_realm else None
        results = self.retreat.run(agent, world, plan.target_shichen, stop_when=stop_when)
        self.bus.publish(AgentStateChanged(agent.agent_id, agent.state.name))

        from model.services.clock_service import summarize_retreat

        summary = summarize_retreat(results, agent.realm)
        return TurnResult(
            retreat_summary=summary, retreat_before_realm=before_realm, retreat_before_cultivation=before_cultivation
        )

    # ---------- 单条事件结算：总线订阅、日程、连锁共用 ----------
    def execute_occurrence(
        self, agent: "Agent", world: "WorldView", occ: GameEventOccurrence, defn: "GameEventDef"
    ) -> TurnResult | None:
        decision = self.arbiter.decide(
            agent.state.name, occ.trigger_source, defn.priority, self._current_priority(agent)
        )
        if decision is ArbitrationDecision.DISCARD:
            return None
        if decision is ArbitrationDecision.ENQUEUE:
            # 奇遇不抢主行为：只挂起，不跑结果池（README 1.7）
            if agent.pending_encounter_id is None:
                self._park_encounter(agent, defn)
            return None

        eval_ctx = agent.as_eval_context(world)
        if defn.predicate and not defn.predicate.evaluate(eval_ctx):
            return TurnResult.rejected("条件未满足。")  # 状态未改、无日志
        new_state = agent.state.try_transition(agent, occ)
        if new_state is None:
            return TurnResult.rejected("现在做不了这个。")
        agent.state = new_state

        ctx = PipelineContext(occ, defn, agent, world, chosen_variant=occ.chosen_variant_index)
        ctx = self.pipeline.run(ctx)
        if ctx.rejected:
            return TurnResult.rejected("条件未满足。")
        # 时间推进：唯一来源是事件时长（README §1 回合驱动决策）
        self.clock.advance_for(agent, defn.duration_shichen)
        agent.event_history.record(
            defn.event_id, occ.occurred_at, defn.tags, occ.chosen_variant_index,
            exclusive_tags=defn.exclusive_tags, cooldown_shichen=defn.cooldown_shichen,
        )
        agent.state = agent.state.settle(agent)  # 不直接赋 IdleState()
        self.bus.publish(AgentStateChanged(agent.agent_id, agent.state.name))
        for spawned in ctx.spawned:  # 连锁：apply 落地后再投递
            self.bus.publish(spawned)

        first = TurnResult.from_one(defn, ctx)
        if ctx.stopped:
            return first
        if occ.trigger_source is TriggerSource.PLAYER and defn.is_command:
            return self._second_stage(agent, world, first)
        return first

    # ---------- 第二段：按新状态抽库内事件 ----------
    def _second_stage(self, agent: "Agent", world: "WorldView", first: TurnResult) -> TurnResult:
        pool = [e for e in self.events.load_event_defs(agent.location_type) if not e.is_command]
        mctx = MatchContext(
            location=agent.location_id,
            location_type=agent.location_type,
            time_shichen=self.clock.now().shichen,
            now=self.clock.now(),
            age=agent.age,
            realm=agent.realm,
            money=agent.money,
            causes=agent.causes,
        )
        candidates = coarse_filter(pool, mctx, agent.as_eval_context(world), agent.event_history)
        now = self.clock.now()
        picked = reweight_and_pick(
            candidates, agent.event_history, self.rng,
            extra_weight=lambda e: tidal_beast_weight_multiplier(e, now),
        )
        if picked is None:
            return first  # 抽空：酒楼无事，状态已由上一步 settle

        if picked.needs_reply:
            self._park_encounter(agent, picked)  # 只叙述、不结算，等下一句
            agent.state = agent.state.settle(agent)  # → EncounterPending
            return first.with_prompt(picked, pick_variant(picked, agent.event_history, self.rng))

        occ2 = self._new_occurrence(agent, picked, TriggerSource.ENCOUNTER)
        ctx2 = self.pipeline.run(PipelineContext(occ2, picked, agent, world, chosen_variant=occ2.chosen_variant_index))
        if ctx2.rejected:
            return first
        self.clock.advance_for(agent, picked.duration_shichen)
        agent.event_history.record(
            picked.event_id, occ2.occurred_at, picked.tags, occ2.chosen_variant_index,
            exclusive_tags=picked.exclusive_tags, cooldown_shichen=picked.cooldown_shichen,
        )
        agent.state = agent.state.settle(agent)
        for spawned in ctx2.spawned:
            self.bus.publish(spawned)
        return first.plus_encounter(picked, ctx2)

    # ---------- 挂起项结算 ----------
    def _try_resolve_pending(self, agent: "Agent", world: "WorldView", raw: str) -> TurnResult | None:
        """命中局部选项才返回；未命中返回 None 由调用方回落全局命令。"""
        pending_def = self.events.get_by_id(agent.pending_encounter_id) if agent.pending_encounter_id else None
        graph = self.scenarios.get(agent.pending_scenario.scenario_id) if agent.pending_scenario else None
        node_id = agent.pending_scenario.current_node_id if agent.pending_scenario else None
        reply = self.parser.parse_reply(raw, pending_def, graph, node_id)
        if reply is None:
            return None
        if reply.dismissed:
            self._abandon_pending(agent)
            return TurnResult.dismissed()
        if agent.pending_scenario is not None and graph is not None:
            return self._advance_scenario(agent, world, graph, node_id, reply.edge_id)
        if pending_def is not None and reply.option_index is not None:
            return self._resolve_reply_option(agent, world, pending_def, reply.option_index)
        return None

    def _resolve_reply_option(
        self, agent: "Agent", world: "WorldView", pending_def: "GameEventDef", option_index: int
    ) -> TurnResult:
        """把 ReplyOption.results 当成一次性结果池，跑同一条 pipeline。

        `synthetic` 复用 pending_def 的 event_id/variants（只换了 result_pool），
        所以 TurnResult.from_one(synthetic, ...) 会把"选了这个选项"渲染成宿主奇遇
        自己的文案——那是"奇遇发生时"的叙述，不是"你选了这个"的叙述，两者不能共用。
        选项的应答文案走 option.response_text（freeform_narrative）；若这条选项还
        链到了下一条事件（ChainEvent 结果或 chain_event_id 字段），直接同步执行并
        把它的叙述接在后面，而不是丢给总线让 _on_occurrence_published 静默处理掉
        （那样结果没人接，玩家会看不到链式事件到底发生了什么）。
        """
        option = pending_def.reply_options[option_index]
        synthetic = replace(pending_def, result_pool=option.results, predicate=None, reply_options=())
        occ = self._new_occurrence(agent, synthetic, TriggerSource.PLAYER)
        ctx = self.pipeline.run(PipelineContext(occ, synthetic, agent, world, chosen_variant=occ.chosen_variant_index))
        self._clear_pending_encounter(agent)
        agent.state = agent.state.settle(agent)
        self.bus.publish(AgentStateChanged(agent.agent_id, agent.state.name))

        spawned_queue = list(ctx.spawned)
        if option.chain_event_id:
            chain_def = self.events.get_by_id(option.chain_event_id)
            if chain_def is not None and not chain_def.is_draft:
                spawned_queue.append(self._new_occurrence(agent, chain_def, TriggerSource.CHAIN))

        chain_result: TurnResult | None = None
        if spawned_queue:
            first_spawned = spawned_queue.pop(0)
            chain_defn = self.events.get_by_id(first_spawned.event_id)
            if chain_defn is not None and not chain_defn.is_draft:
                chain_result = self.execute_occurrence(agent, world, first_spawned, chain_defn)
        for spawned in spawned_queue:  # 极少见的多重连锁：其余的仍走总线，只是叙述不合并
            self.bus.publish(spawned)

        result = TurnResult(freeform_narrative=option.response_text or None)
        if chain_result is not None and chain_result.command_event_id:
            result = replace(
                result,
                encounter_event_id=chain_result.command_event_id,
                encounter_variant=chain_result.command_variant,
                encounter_diff=chain_result.command_diff,
            )
        return result

    def _advance_scenario(
        self, agent: "Agent", world: "WorldView", graph, node_id: str | None, chosen_edge_id: str | None
    ) -> TurnResult:
        from model.services.scenario_executor import ScenarioExecutor

        executor = ScenarioExecutor()
        next_node = executor.advance(graph, node_id, agent.as_eval_context(world), chosen_edge_id)
        if next_node is None:
            self._clear_pending_scenario(agent)  # 无边满足：本条事件内流程结束
            agent.state = agent.state.settle(agent)
            return TurnResult.dismissed()

        synthetic = replace(
            self.events.get_by_id(agent.pending_scenario.host_event_id) or _blank_event_def(next_node.node_id),
            result_pool=next_node.results,
            predicate=None,
            reply_options=(),
        )
        occ = self._new_occurrence(agent, synthetic, TriggerSource.PLAYER)
        ctx = self.pipeline.run(PipelineContext(occ, synthetic, agent, world, chosen_variant=occ.chosen_variant_index))

        # 推进到新节点：还有出边则继续挂起，否则清空 pending_scenario
        if graph.edges_from(next_node.node_id):
            agent.pending_scenario = replace(agent.pending_scenario, current_node_id=next_node.node_id)
        else:
            self._clear_pending_scenario(agent)
        agent.state = agent.state.settle(agent)
        for spawned in ctx.spawned:
            self.bus.publish(spawned)
        result = TurnResult.from_one(synthetic, ctx)
        return replace(result, scenario_node_id=next_node.node_id)

    # ---------- 挂起态辅助 ----------
    def _park_encounter(self, agent: "Agent", defn: "GameEventDef") -> None:
        from model.domain.diff import AppliedDiff, apply_agent_diff

        apply_agent_diff(agent, AppliedDiff(pending_encounter_set=defn.event_id))

    def _clear_pending_encounter(self, agent: "Agent") -> None:
        from model.domain.diff import AppliedDiff, apply_agent_diff

        apply_agent_diff(agent, AppliedDiff(pending_encounter_set=""))

    def _clear_pending_scenario(self, agent: "Agent") -> None:
        from model.domain.diff import AppliedDiff, apply_agent_diff

        apply_agent_diff(agent, AppliedDiff(pending_scenario_set=None))

    def _abandon_pending(self, agent: "Agent") -> None:
        """玩家说了无关的话：挂起项按"错过"丢弃，经 diff 落库，不留悬空 id。"""
        if agent.pending_encounter_id is not None:
            self._clear_pending_encounter(agent)
        if agent.pending_scenario is not None:
            self._clear_pending_scenario(agent)
        agent.state = agent.state.settle(agent)

    # ---------- 杂项 ----------
    def _current_priority(self, agent: "Agent") -> int | None:
        """MVP 是同步回合制：every execute_occurrence 结束都会 settle() 离开
        acting——下一条事件到达时 agent 永远不会"正处于 acting"，故此处恒为
        None；仲裁器里的 acting 分支为未来异步/并发主行为预留。"""
        return None

    def _new_occurrence(self, agent: "Agent", defn: "GameEventDef", source: TriggerSource) -> GameEventOccurrence:
        return GameEventOccurrence(
            defn.event_id, source, agent.agent_id, self.clock.now(),
            chosen_variant_index=pick_variant(defn, agent.event_history, self.rng),
        )


def _blank_event_def(node_id: str) -> "GameEventDef":
    """流程图节点找不到宿主事件定义时的兜底占位（正常不应发生：pending_scenario
    的 host_event_id 必是已发布事件）。"""
    from model.domain.events import GameEventDef

    return GameEventDef(
        event_id=f"__scenario_node__{node_id}",
        applicable_locations=("*",),
        applicable_time=None,
        predicate=None,
        weight=0.0,
        duration_shichen=0,
        cooldown_shichen=0,
        max_trigger_per_agent=None,
        exclusive_tags=(),
        priority=5,
        tags=(),
        aliases=(),
        result_pool=(),
        variants=(),
    )


def _default_move_def() -> "GameEventDef":
    """content 侧没有注册 event_id="move" 的兜底（GAME_DESIGN §3.1："去{地点}"是
    系统命令，不强依赖内容库；有内容库版本时优先用它的谓词/时长/变体文案）。"""
    from model.domain.events import EventVariant, GameEventDef

    return GameEventDef(
        event_id=MOVE_EVENT_ID,
        applicable_locations=("*",),
        applicable_time=None,
        predicate=None,
        weight=1.0,
        duration_shichen=1,
        cooldown_shichen=0,
        max_trigger_per_agent=None,
        exclusive_tags=(),
        priority=5,
        tags=("生活",),
        aliases=(),
        result_pool=(),
        variants=(EventVariant("你来到了{地点}。"),),
        is_command=True,
        is_draft=False,
    )
