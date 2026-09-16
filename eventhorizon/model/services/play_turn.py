"""model/services/play_turn.py — 对局两段循环（唯一编排处，对应 README §3.1）。

对局唯一入口：玩家聊天、NPC 日程、时钟到点，都 EventBus.publish 一条已解析好的
GameEventOccurrence（或先 publish 命令意图，由本服务订阅后补全）。顺序：仲裁 →
谓词校验 → 状态机 → 责任链产出 diff → 一次性 apply → 记日志 → 再决定是否抽第二段。

状态类不持有 EventBus；本服务在转换成功后 publish(AgentStateChanged)。
服务对象一律无跨回合状态——挂起态（pending_encounter_id / pending_scenario）全部
存在 Agent 上，PlayTurnService 自身不缓存任何跨轮次数据。
"""
from __future__ import annotations

import logging
import random
from dataclasses import replace
from typing import TYPE_CHECKING

from model.domain.diff import AppliedDiff, HistoryRecord, apply_agent_diff
from model.domain.events import EventVariant, GameEventOccurrence, TriggerSource
from model.domain.results import ItemConsume, StateChange
from model.domain.system_events import AgentStateChanged, DeathEvent
from model.services.arbiter import ArbitrationDecision, EventArbiter
from model.services.chat_parser import MOVE_EVENT_ID, ParsedCommand, QUERY_EVENT_IDS, RETREAT_START_EVENT_ID
from model.services.death_service import DeathService, RebirthPath
from model.services.live_authoring_coordinator import LiveAuthoringCoordinator
from model.services.matching import (
    MatchContext,
    build_context_embedding,
    build_narrative_context_text,
    coarse_filter,
    embed_safely,
    find_best_matching_command,
    narrative_fit_multiplier,
    pick_variant,
    reweight_and_pick,
    tidal_beast_weight_multiplier,
)
from model.services.pipeline import Pipeline, PipelineContext
from model.services.retreat_intent_parser import parse_retreat_duration, stop_when_realm_reached
from model.services.turn_result import TurnResult

# 终极兜底用的预置事件（content/events/commands.py::IDLE_WANDER，README §1.13）。
# 不用 chat_parser.py 那套 MOVE_EVENT_ID/RETREAT_START_EVENT_ID 常量的路子，因为
# idle_wander 不是系统命令，只是一个普通的、seed 时就发布好的命令型事件——直接按
# event_id 字符串查库即可，跟 EAT/MEDITATE 等其他内置命令没有本质区别。
IDLE_WANDER_EVENT_ID = "idle_wander"


if TYPE_CHECKING:
    from model.domain.agent import Agent
    from model.domain.balance import BalanceTable
    from model.domain.events import GameEventDef
    from model.domain.map import WorldView
    from model.services.chat_parser import ChatParser
    from model.services.clock_service import GameClock, RetreatService
    from model.services.death_service import DeathService
    from model.services.event_bus import EventBus
    from model.services.live_narrative_writer import LlmClient
    from model.services.ports import EmbeddingPort, EventLogStore, EventRepository, ScenarioRepository

_logger = logging.getLogger("eventhorizon.play_turn")


_RETREAT_PROMPT_TEXT = '要闭关多久？（可以说"十年""到金丹为止"或"随便"）'
_RETREAT_UNPARSEABLE_TEXT = '没听懂要闭关多久，你可以说"十年""到金丹为止"或"随便"。'
_FORCE_EVENT_BY_REASON = {"天劫": "qi_deviation", "走火入魔": "qi_deviation"}
_REBIRTH_ALIASES = {
    "转世": RebirthPath.REINCARNATE,
    "夺舍": RebirthPath.POSSESS,
    "继承": RebirthPath.INHERIT,
}


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
        embedding: "EmbeddingPort | None" = None,
        narrative_writer: "LlmClient | None" = None,
        death_service: "DeathService | None" = None,
        npc_provider=None,
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
        self.embedding = embedding
        self.narrative_writer = narrative_writer
        self.death_service = death_service or DeathService()
        self.npc_provider = npc_provider
        # embedding/narrative_writer 都是可选的（未配置就是 None）：embedding 只用于
        # predicate_text 的向量相似度判定；narrative_writer 是 LlmEventWriter（README
        # 对局第二段表格），事件命中但 variants 为空时现场补一句文案，见
        # _ensure_variants()。README 5.3 对局隔离针对的是"录入侧大模型草稿生成"那个
        # 端口，不是这两个——V2 向量匹配/LlmEventWriter 本来就该在对局路径里用。
        # 实时创作（README §1.12 的有意识例外）整摊逻辑都在 LiveAuthoringCoordinator
        # 里，本类只在解析彻底失败（规则 + 向量都没匹配上）时委派过去，不自己拼
        # LiveContentAuthor——见 live_authoring_coordinator.py 顶部说明。它复用同一个
        # narrative_writer 客户端（同一个 LlmClient Protocol）。
        self.live_authoring = LiveAuthoringCoordinator(events, narrative_writer, embedding=embedding)
        self.bus.subscribe(GameEventOccurrence, self._on_occurrence_published)

    def _ensure_variants(self, defn: "GameEventDef") -> "GameEventDef":
        """variants 留空 = 用户在编辑器里没填（或压根没在表单里露出这个字段），
        交给 LlmEventWriter 现场补一句，并存回仓库——下次同一事件命中就不用再现场
        生成（README："临时补一条，建议事后再走…落库"）。只在这里对"确实从仓库
        按 id 取到的原始定义"调用；调用方必须保证传进来的不是 replace() 造出来的
        局部 synthetic（那种一 save 会把 result_pool/predicate 这些被临时改写的
        字段也存回去，冲掉原定义）。"""
        if defn.variants:
            return defn
        text = self.live_authoring.generate_variant_text(defn.event_id, defn.tags)
        patched = replace(defn, variants=(EventVariant(text=text),))
        self.events.save_event_def(patched)
        return patched

    # ---------- 总线订阅：日程/连锁等通过 publish 投递的 Occurrence 走这里 ----------
    def _on_occurrence_published(self, occ: GameEventOccurrence) -> None:
        defn = self.events.get_by_id(occ.event_id)
        if defn is None or defn.is_draft:
            return
        defn = self._ensure_variants(defn)
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
        """一次玩家输入的总路由。优先级从高到低，前一档接住了就不往下走：

        0. **回合级副作用**——计轮数、重置大模型预算、结算上一条伏笔的延迟结果。
           都不消费 raw，不提前返回。
        1. **闭关时长追问**（README §3.5）：答不上来就一直卡在这一档。
        2. **奇遇/流程图挂起态**（README 1.11）：先试局部选项，没命中就按"错过"
           丢弃挂起项，继续往下当普通命令解析。
        3. **追问补全**（README §1.12）：上一句被判信息不全时挂起等这一句。
        4. **常规命令**：规则解析 → 向量意图 → 实时创作 → idle_wander 终极兜底，
           四层依次尝试（README §1.13）。
        """
        if agent.state.name == "dead":
            return self._handle_rebirth_choice(agent, world, raw)

        # —— 0) 回合级副作用 ——
        # 每轮输入都计数（成功/失败都算），驱动"提示只出现在前 3 轮"（README §3.2）
        apply_agent_diff(agent, AppliedDiff(attr_deltas=(("turn_count", 1.0),)))
        # 这一回合的大模型调用预算从零开始算（见 live_authoring_coordinator.LlmCallBudget）
        self.live_authoring.begin_turn()
        # 延迟结果：问一句"这句话算不算把上一条伏笔翻篇了"，落地或续挂，
        # 不吃掉 raw（见 model/domain/agent.py::PendingLiveResult）
        self.live_authoring.maybe_conclude_deferred_result(agent, raw)

        # —— 1) 闭关时长追问 ——
        if agent.pending_retreat_prompt:
            return self._handle_retreat_answer(agent, world, raw)

        # —— 2) 奇遇 / 流程图挂起态 ——
        if agent.pending_scenario is not None or agent.pending_encounter_id is not None:
            resolved = self._try_resolve_pending(agent, world, raw)
            if resolved is not None:
                return resolved
            self._abandon_pending(agent)  # 玩家改主意：挂起项按"错过"清掉，经 diff 落库

        # —— 3) 追问补全 ——
        if agent.pending_clarification is not None:
            return self._resolve_clarification(agent, world, raw)

        # —— 4) 常规命令的四层兜底链 ——
        cmd = self.parser.parse(raw, agent.scene_focus)
        if cmd is None:
            cmd = self._match_command_by_intent(raw, agent)
        if cmd is None:
            outcome = self.live_authoring.author_command(agent, raw)
            resolved = self.live_authoring.resolve_command_outcome(agent, outcome, raw, prior_attempts=0)
            if resolved.kind == "replied":
                return resolved.reply
            cmd = resolved.value
        if cmd is None:
            return self._terminal_fallback(agent, world)
        return self._dispatch_command(agent, world, cmd)

    def _dispatch_command(self, agent: "Agent", world: "WorldView", cmd) -> TurnResult:
        """一条已经确定下来的 ParsedCommand 该怎么执行——不管它是规则解析器/向量
        兜底/实时创作/追问补全哪条路径给出来的，落地逻辑都是同一套。"""
        if cmd.is_query or cmd.event_id in QUERY_EVENT_IDS:
            # 只读查询命令由 controller 直接调只读服务处理，不该走到这里；防御性拒绝。
            return TurnResult.rejected("这个只能查，改变不了什么，换句话说说你想做什么？")
        if cmd.event_id == MOVE_EVENT_ID:
            return self._handle_move(agent, world, cmd)
        if cmd.event_id == RETREAT_START_EVENT_ID:
            return self._handle_retreat_start(agent)

        defn = self.events.get_by_id(cmd.event_id)
        if defn is None or defn.is_draft or not defn.is_command:
            return self._terminal_fallback(agent, world)
        defn = self._ensure_variants(defn)
        occ = self._new_occurrence(agent, defn, TriggerSource.PLAYER)
        return self.execute_occurrence(agent, world, occ, defn) or TurnResult.rejected("现在做不了这个。")

    def _resolve_clarification(self, agent: "Agent", world: "WorldView", raw: str) -> TurnResult:
        """追问回来的这句话，跟玩家最初那句拼在一起重新尝试创作——不重新走规则
        解析/向量兜底（那两层已经在第一次就试过判定不了了），直接回到失败的那
        一层继续。成不成、要不要再问一次，都由 LiveAuthoringCoordinator 里那套
        统一的追问上限逻辑决定（跟"第一次就失败"走的是同一段代码）。"""
        pending = agent.pending_clarification
        combined = f"{pending.original_text}（补充：{raw}）"
        if pending.kind == "command":
            outcome = self.live_authoring.author_command(agent, combined)
            resolved = self.live_authoring.resolve_command_outcome(agent, outcome, combined, pending.attempts)
            if resolved.kind == "replied":
                return resolved.reply
            if resolved.kind == "failed":
                return self._terminal_fallback(agent, world)
            return self._dispatch_command(agent, world, resolved.value)
        outcome = self.live_authoring.author_destination(agent, world, combined)
        resolved = self.live_authoring.resolve_location_outcome(agent, world, outcome, combined, pending.attempts)
        if resolved.kind == "replied":
            return resolved.reply
        if resolved.kind == "failed":
            return self._terminal_fallback(agent, world)
        return self._complete_move(agent, world, resolved.value)

    def _terminal_fallback(self, agent: "Agent", world: "WorldView") -> TurnResult:
        """终极兜底原则（README §1.13）：规则解析/向量意图/实时创作（含追问）
        全部走不通时，绝不能让玩家看到干瘪的拒绝。前 3 轮软性引导
        （_soft_guidance_message 会给出招式举例）保留不变；从第 4 轮起，
        原本落在这里的"听不懂，再说一次？"改由 _idle_wander_fallback 接管——
        直接执行预置的 idle_wander 事件，给玩家一段"什么都没发生，但话确实被
        听懂了"的旁白，并按其配置消耗一点时间，而不是被系统当场拒绝。"""
        if agent.turn_count > 3:
            return self._idle_wander_fallback(agent, world)
        return TurnResult.parse_failed(self._soft_guidance_message(agent, world))

    def _idle_wander_fallback(self, agent: "Agent", world: "WorldView") -> TurnResult:
        defn = self.events.get_by_id(IDLE_WANDER_EVENT_ID)
        if defn is None or defn.is_draft or not defn.is_command:
            # 预置事件本该总是存在——防御性兜底，理论上不会走到这里。
            return TurnResult.parse_failed(self._soft_guidance_message(agent, world))
        defn = self._ensure_variants(defn)
        occ = self._new_occurrence(agent, defn, TriggerSource.PLAYER)
        return self.execute_occurrence(agent, world, occ, defn) or TurnResult.parse_failed(
            self._soft_guidance_message(agent, world)
        )

    def _soft_guidance_message(self, agent: "Agent", world: "WorldView") -> str:
        """README §3.2：前 3 轮给软性引导（从当前地点合格池现取别名举例），
        之后回归简单的"听不懂"，避免变成事实上的教程文本。"""
        if agent.turn_count > 3:
            return "听不懂，再说一次？"
        pool = [e for e in self.events.load_event_defs(agent.location_type) if e.is_command and not e.is_draft]
        examples = self.parser.suggest_aliases(pool, n=2)
        if not examples:
            return "听不懂，再说一次？"
        examples_text = "或".join(f'"{a}"' for a in examples)
        return f"听不懂，要不试试{examples_text}？"

    def _match_command_by_intent(self, raw: str, agent: "Agent") -> "ParsedCommand | None":
        """chat_parser.py 别名精确/子串匹配失败后的向量兜底（chat_parser.py 自己
        文档里"V2 上向量匹配"那条既定路线图，不是新方向）——"吃点东西"这类自然
        语言，跟当前地点已发布命令型事件的 narrative_embedding 比语义相似度。
        embedding 未配置/调用失败都自然返回空向量，find_best_matching_command
        见到空查询向量直接判不命中（fail-closed，不影响现有行为）。"""
        pool = [e for e in self.events.load_event_defs(agent.location_type) if e.is_command and not e.is_draft]
        pool = [self._ensure_narrative_embedding(e) for e in pool]
        query = embed_safely(self.embedding, raw)
        matched = find_best_matching_command(pool, query)
        if matched is None:
            return None
        return ParsedCommand(event_id=matched.event_id, location_hint=None, target=None, args={})

    def _ensure_narrative_embedding(self, defn: "GameEventDef") -> "GameEventDef":
        """跟 _ensure_variants 同一个"缺了就现算一次、存回仓库"套路：内容库里
        手工/AI 录入的事件保存时（admin_controller.py::save_event）已经算好
        narrative_embedding 了，但 content/events/*.py 里那些随游戏内置、走
        seed_all() 直接 save_event_def() 落库的命令（吃饭/打坐这些）从来没经过
        那条计算路径，narrative_embedding 天生是空的——不补上这一步，向量意图
        兜底对着游戏自带的命令永远匹配不上，"吃点东西"这类自然语言只会一直
        "听不懂"。只在真的要用到向量匹配（chat_parser 精确匹配已经失败）时才算，
        不在每次装载事件池时都算一遍。"""
        if defn.narrative_embedding:
            return defn
        text = " ".join(list(defn.tags) + list(defn.aliases) + [v.text for v in defn.variants]).strip()
        if not text:
            return defn
        patched = replace(defn, narrative_embedding=embed_safely(self.embedding, text))
        self.events.save_event_def(patched)
        return patched

    # ---------- 系统命令：move / retreat_start（README §3.3，非库内事件）----------
    def _handle_move(self, agent: "Agent", world: "WorldView", cmd) -> TurnResult:
        if agent.state.name != "idle":
            return TurnResult.rejected("现在走不开。")
        destination = world.find_location_by_name(cmd.location_hint) if cmd.location_hint else None
        if destination is None and cmd.location_hint:
            outcome = self.live_authoring.author_destination(agent, world, cmd.location_hint)
            resolved = self.live_authoring.resolve_location_outcome(
                agent, world, outcome, cmd.location_hint, prior_attempts=0
            )
            if resolved.kind == "replied":
                return resolved.reply
            destination = resolved.value
        if destination is None:
            hint = cmd.location_hint or "那里"
            return TurnResult.rejected(f"找不到「{hint}」这个地方。")
        return self._complete_move(agent, world, destination)

    def _complete_move(self, agent: "Agent", world: "WorldView", destination) -> TurnResult:
        base = self._ensure_variants(self.events.get_by_id(MOVE_EVENT_ID) or default_move_def())
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
        if plan.is_default_suggestion:
            from model.domain.time import SHICHEN_PER_YEAR

            years = max(1, round(plan.target_shichen / SHICHEN_PER_YEAR))
            return TurnResult(
                freeform_narrative=f"{plan.description}。确定的话直接说年数，比如「{years}年」。"
            )

        apply_agent_diff(agent, AppliedDiff(pending_retreat_prompt_set=False))

        before_realm, before_cultivation = agent.realm, agent.cultivation
        stop_when = stop_when_realm_reached(plan.stop_at_realm) if plan.stop_at_realm else None
        results = self.retreat.run(agent, world, plan.target_shichen, stop_when=stop_when)
        self.bus.publish(AgentStateChanged(agent.agent_id, agent.state.name))

        from model.services.clock_service import summarize_retreat

        summary = summarize_retreat(results, agent.realm)
        retreat_result = TurnResult(
            retreat_summary=summary, retreat_before_realm=before_realm, retreat_before_cultivation=before_cultivation
        )
        if agent.lifespan_left <= 0:
            death = self._maybe_die(agent, "寿元耗尽")
            return death or retreat_result
        if summary.interrupted_by_force and summary.force_reason:
            force_id = _FORCE_EVENT_BY_REASON.get(summary.force_reason)
            if force_id:
                force_def = self.events.get_by_id(force_id)
                if force_def is not None and not force_def.is_draft:
                    force_def = self._ensure_variants(force_def)
                    occ = self._new_occurrence(agent, force_def, TriggerSource.FORCE)
                    forced = self.execute_occurrence(agent, world, occ, force_def)
                    if forced is not None:
                        return forced
        return retreat_result

    # ---------- 系统触发源复用入口（日程/其它非玩家来源）----------
    def trigger(
        self, agent: "Agent", world: "WorldView", defn: "GameEventDef", source: TriggerSource
    ) -> TurnResult | None:
        """给 schedule_service 等系统触发源一个公开入口，复用同一条
        execute_occurrence 路径——不止 handle_player_text 能进两段式流水线（README
        1.5.2："以 TriggerSource=schedule 走 execute_occurrence，与玩家侧同一条路径"）。
        变体选择同样走 pick_variant，不是恒 0。"""
        defn = self._ensure_variants(defn)
        occ = self._new_occurrence(agent, defn, source)
        return self.execute_occurrence(agent, world, occ, defn)

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
        previous_state = agent.state
        new_state = agent.state.try_transition(agent, occ)
        if new_state is None:
            return TurnResult.rejected("现在做不了这个。")
        agent.state = new_state

        if occ.trigger_source is TriggerSource.PLAYER and defn.needs_reply:
            # 分支事件：只叙述、不结算、不收时间；但要记事件历史，冷却/次数才生效。
            self._park_encounter(agent, defn)
            self._apply_history(agent, occ, defn)
            agent.state = agent.state.settle(agent)
            variant = pick_variant(defn, agent.event_history, self.rng)
            return TurnResult().with_prompt(defn, variant)

        ctx = self._run_pipeline(agent, world, occ, defn)
        if ctx.rejected:
            agent.state = previous_state
            return TurnResult.rejected("条件未满足。")
        self._charge_time(agent, occ, defn)
        death = self._maybe_die(agent, "寿元耗尽")
        self._settle_and_publish(agent, ctx, announce_state=True)

        first = TurnResult.from_one(defn, ctx)
        if death is not None:
            return death
        if ctx.stopped:
            return first
        # 上一条实时创作事件的延迟结果还没收尾时，不抽新的第二段奇遇——避免
        # 一条伏笔还悬着，又平白冒出一个不相关的新奇遇，破坏聊天的连贯性
        # （PendingLiveResult 类注释）。命令本身该怎么结算不受影响，只是不再
        # 往上叠加随机奇遇。
        if occ.trigger_source is TriggerSource.PLAYER and defn.is_command and agent.pending_live_result is None:
            return self._second_stage(agent, world, first)
        return first

    # ---------- 第二段：按新状态抽库内事件 ----------
    def _second_stage(self, agent: "Agent", world: "WorldView", first: TurnResult) -> TurnResult:
        pool = [e for e in self.events.load_event_defs(agent.location_type) if not e.is_command]
        now = self.clock.now()
        mctx = MatchContext(
            location=agent.location_id,
            location_type=agent.location_type,
            time_shichen=now.shichen,
            now=now,
            age=agent.age,
            realm=agent.realm,
            money=agent.money,
            causes=agent.causes,
            context_embedding=build_context_embedding(
                self.embedding, location_type=agent.location_type, realm=agent.realm, money=agent.money, age=agent.age
            ),
            narrative_context_embedding=embed_safely(
                self.embedding,
                build_narrative_context_text(
                    location=agent.location_id, location_type=agent.location_type, realm=agent.realm,
                    money=agent.money, age=agent.age, time_shichen=now.shichen, flags=agent.flags,
                ),
            ),
        )
        candidates = coarse_filter(pool, mctx, agent.as_eval_context(world), agent.event_history)
        picked = reweight_and_pick(
            candidates, agent.event_history, self.rng,
            extra_weight=lambda e: tidal_beast_weight_multiplier(e, now) * narrative_fit_multiplier(e, mctx),
        )
        if picked is None:
            return first  # 抽空：酒楼无事，状态已由上一步 settle
        picked = self._ensure_variants(picked)

        if picked.needs_reply:
            self._park_encounter(agent, picked)
            self._apply_history(agent, self._new_occurrence(agent, picked, TriggerSource.ENCOUNTER), picked)
            agent.state = agent.state.settle(agent)
            return first.with_prompt(picked, pick_variant(picked, agent.event_history, self.rng))

        occ2 = self._new_occurrence(agent, picked, TriggerSource.ENCOUNTER)
        ctx2 = self._run_pipeline(agent, world, occ2, picked)
        if ctx2.rejected:
            return first
        self._charge_time(agent, occ2, picked)
        death = self._maybe_die(agent, "寿元耗尽")
        self._settle_and_publish(agent, ctx2, announce_state=False)
        if death is not None:
            return death
        return first.plus_encounter(picked, ctx2)

    # ---------- 结算三件套：四条结算路径共用，差异只体现在"调不调 _charge_time" ----------
    #
    # 对局里有四条路径会跑结果池：主命令（execute_occurrence）、第二段奇遇
    # （_second_stage）、分支选项（_resolve_reply_option）、流程图节点
    # （_advance_scenario）。它们的骨架是同一套"跑责任链 → [推进时间] → 落状态 →
    # 投递连锁"，以前四处各抄一遍。抽成下面三个小函数而不是一个带四个布尔开关的
    # 大函数：开关版读起来比重复更糟，而拆成三个之后，**某条路径"少调了哪一个"
    # 本身就是说明**——见 _charge_time 的注释。

    def _run_pipeline(
        self, agent: "Agent", world: "WorldView", occ: GameEventOccurrence, defn: "GameEventDef", *,
        record_history: bool = True,
    ):
        ctx = PipelineContext(occ, defn, agent, world, chosen_variant=occ.chosen_variant_index)
        if record_history:
            ctx.diff = AppliedDiff(history_records=(self._history_record(occ, defn),))
        return self.pipeline.run(ctx)

    def _history_record(self, occ: GameEventOccurrence, defn: "GameEventDef") -> HistoryRecord:
        return HistoryRecord(
            event_id=defn.event_id,
            at=occ.occurred_at,
            tags=defn.tags,
            variant=occ.chosen_variant_index,
            exclusive_tags=defn.exclusive_tags,
            cooldown_shichen=defn.cooldown_shichen,
        )

    def _apply_history(self, agent: "Agent", occ: GameEventOccurrence, defn: "GameEventDef") -> None:
        apply_agent_diff(agent, AppliedDiff(history_records=(self._history_record(occ, defn),)))

    def _charge_time(self, agent: "Agent", occ: GameEventOccurrence, defn: "GameEventDef") -> None:
        """推进游戏时间。事件历史已并入 pipeline diff 或挂起时的 _apply_history。

        分支选项和流程图节点故意不调：产品决策「分支不消耗时间」。
        """
        self.clock.advance_for(agent, defn.duration_shichen)

    def _settle_and_publish(self, agent: "Agent", ctx, *, announce_state: bool) -> None:
        """落状态机 + 投递连锁。announce_state 对应"这次状态变化要不要广播
        AgentStateChanged"——主命令和分支选项是玩家主动行为的落点，要广播；第二段
        奇遇和流程图节点挂在同一次玩家输入之内，状态最终由外层那次广播覆盖，
        不重复发。"""
        agent.state = agent.state.settle(agent)  # 不直接赋 IdleState()
        if announce_state:
            self.bus.publish(AgentStateChanged(agent.agent_id, agent.state.name))
        for spawned in ctx.spawned:  # 连锁：apply 落地后再投递
            self.bus.publish(spawned)

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
        pending_def = self._ensure_variants(pending_def)
        option = pending_def.reply_options[option_index]
        unaffordable = _results_unaffordable(agent, option.results)
        if unaffordable:
            return TurnResult.rejected(unaffordable)
        synthetic = replace(pending_def, result_pool=option.results, predicate=None, reply_options=())
        occ = self._new_occurrence(agent, synthetic, TriggerSource.PLAYER)
        ctx = self._run_pipeline(agent, world, occ, synthetic, record_history=False)
        self._clear_pending_encounter(agent)
        # 注意这里**没有** _charge_time：分支不消耗时间（产品决策，见该函数注释）。
        # 连锁事件的时间由它自己那次 execute_occurrence 负责，不在这里代收。
        agent.state = agent.state.settle(agent)
        self.bus.publish(AgentStateChanged(agent.agent_id, agent.state.name))

        # 连锁要单独处理（不能直接用 _settle_and_publish）：第一条连锁是同步执行、
        # 叙述要合并进本次回复的，其余才走总线。
        spawned_queue = list(ctx.spawned)
        if option.chain_event_id:
            chain_def = self.events.get_by_id(option.chain_event_id)
            if chain_def is not None and not chain_def.is_draft:
                chain_def = self._ensure_variants(chain_def)
                spawned_queue.append(self._new_occurrence(agent, chain_def, TriggerSource.CHAIN))

        chain_result: TurnResult | None = None
        if spawned_queue:
            first_spawned = spawned_queue.pop(0)
            chain_defn = self.events.get_by_id(first_spawned.event_id)
            if chain_defn is not None and not chain_defn.is_draft:
                chain_defn = self._ensure_variants(chain_defn)
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

        host_def = self._ensure_variants(
            self.events.get_by_id(agent.pending_scenario.host_event_id) or _blank_event_def(next_node.node_id)
        )
        unaffordable = _results_unaffordable(agent, next_node.results)
        if unaffordable:
            return TurnResult.rejected(unaffordable)
        synthetic = replace(host_def, result_pool=next_node.results, predicate=None, reply_options=())
        occ = self._new_occurrence(agent, synthetic, TriggerSource.PLAYER)
        ctx = self._run_pipeline(agent, world, occ, synthetic, record_history=False)

        # 推进到新节点：还有出边则继续挂起，否则清空 pending_scenario
        if graph.edges_from(next_node.node_id):
            apply_agent_diff(
                agent,
                AppliedDiff(pending_scenario_set=replace(agent.pending_scenario, current_node_id=next_node.node_id)),
            )
        else:
            self._clear_pending_scenario(agent)
        # 同样**没有** _charge_time：走流程图的一个节点也是"在已发生的场景里做选择"，
        # 不另外计时（见 _charge_time 注释里的产品决策）。
        agent.state = agent.state.settle(agent)
        for spawned in ctx.spawned:
            self.bus.publish(spawned)
        result = TurnResult.from_one(synthetic, ctx)
        return replace(result, scenario_node_id=next_node.node_id)

    # ---------- 挂起态辅助 ----------
    def _park_encounter(self, agent: "Agent", defn: "GameEventDef") -> None:
        apply_agent_diff(agent, AppliedDiff(pending_encounter_set=defn.event_id))

    def _clear_pending_encounter(self, agent: "Agent") -> None:
        apply_agent_diff(agent, AppliedDiff(pending_encounter_set=""))

    def _clear_pending_scenario(self, agent: "Agent") -> None:
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


    def _maybe_die(self, agent: "Agent", cause: str) -> TurnResult | None:
        if agent.lifespan_left > 0 or agent.state.name == "dead":
            return None
        outcome = self.death_service.handle_death(agent, self.clock.now(), cause)
        self.bus.publish(DeathEvent(agent.agent_id, self.clock.now(), cause))
        self.bus.publish(AgentStateChanged(agent.agent_id, agent.state.name))
        return TurnResult(freeform_narrative=_rebirth_prompt(outcome.epitaph, agent, self.balance, self._npcs()))

    def _handle_rebirth_choice(self, agent: "Agent", world: "WorldView", raw: str) -> TurnResult:
        path = None
        stripped = raw.strip()
        for alias, candidate in _REBIRTH_ALIASES.items():
            if alias in stripped:
                path = candidate
                break
        if path is None:
            epitaph = compose_epitaph_fallback(agent)
            return TurnResult(freeform_narrative=_rebirth_prompt(epitaph, agent, self.balance, self._npcs()))
        npcs = self._npcs()
        if path is RebirthPath.REINCARNATE:
            self.death_service.reincarnate(agent)
        else:
            if self.balance is None:
                return TurnResult.rejected("此路不通。")
            options = self.death_service.available_rebirth_paths(agent, self.balance, npcs)
            chosen = next((o for o in options if o.path is path), None)
            if chosen is None or not chosen.available:
                reason = chosen.reason if chosen is not None else "此路不通。"
                return TurnResult.rejected(reason)
            if not npcs:
                return TurnResult.rejected("附近没有可以接手的人。")
            if path is RebirthPath.POSSESS:
                self.death_service.possess(agent, npcs[0])
            else:
                self.death_service.inherit(agent, npcs[0])
        self.bus.publish(AgentStateChanged(agent.agent_id, agent.state.name))
        return TurnResult(freeform_narrative=f"你选择了{path.value}。新的旅途开始了。")

    def _npcs(self) -> list:
        if self.npc_provider is None:
            return []
        return [a for a in self.npc_provider() if getattr(a, "is_npc", False)]


def _rebirth_prompt(epitaph: str, agent, balance, hosts) -> str:
    from model.services.death_service import DeathService

    lines = [
        f"[系统] {epitaph}",
        "你的旅程结束了。接下来——",
    ]
    service = DeathService()
    if balance is not None:
        for option in service.available_rebirth_paths(agent, balance, hosts):
            mark = option.path.value if option.available else f"{option.path.value}（不可选）"
            lines.append(f"  {mark}：{option.reason}")
    lines.append('（打字说出你的选择，比如"转世"）')
    return "\n".join(lines)


def compose_epitaph_fallback(agent) -> str:
    return f"{agent.agent_id}已故。打字选择转世、夺舍或继承。"


def _results_unaffordable(agent: "Agent", results) -> str | None:
    for item in results:
        if isinstance(item, StateChange) and item.field == "money" and item.delta is not None:
            if agent.money + item.delta < 0:
                return "你囊中羞涩，买不起。"
        if isinstance(item, ItemConsume) and not agent.inventory.has(item.item_id, item.n):
            return f"你没有足够的{item.item_id}。"
    return None


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


def default_move_def() -> "GameEventDef":
    """content 侧没有注册 event_id="move" 的兜底（README §3.3："去{地点}"是
    系统命令，不强依赖内容库；有内容库版本时优先用它的谓词/时长/变体文案）。
    公开（不带下划线前缀）：chat_controller.py 渲染叙述时也要能拿到同一份定义——
    _handle_move 用的是它合成出来的 GameEventDef，不是 events 仓库里的真实记录，
    controller 侧按 event_id 查仓库是查不到的，两边必须用同一个兜底函数，不能各
    编一份、内容还可能对不上。"""
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
