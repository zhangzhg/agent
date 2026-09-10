"""model/services/play_turn.py — 对局两段循环（唯一编排处，对应 README 2.2 / 4.9）。

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
import uuid
from dataclasses import replace
from typing import TYPE_CHECKING

from model.domain.diff import AppliedDiff, apply_agent_diff
from model.domain.events import EventVariant, GameEventOccurrence, TriggerSource
from model.domain.results import StateChange
from model.domain.system_events import AgentStateChanged
from model.services.arbiter import ArbitrationDecision, EventArbiter
from model.services.chat_parser import MOVE_EVENT_ID, ParsedCommand, QUERY_EVENT_IDS, RETREAT_START_EVENT_ID
from model.services.event_validation import ValidationCatalog, validate_event_def
from model.services.live_content_author import LiveAuthorOutcome, LiveContentAuthor
from model.services.live_narrative_writer import generate_live_variant_text
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

if TYPE_CHECKING:
    from model.domain.agent import Agent
    from model.domain.balance import BalanceTable
    from model.domain.events import GameEventDef
    from model.domain.map import Location, WorldView
    from model.services.chat_parser import ChatParser
    from model.services.clock_service import GameClock, RetreatService
    from model.services.event_bus import EventBus
    from model.services.live_narrative_writer import LlmClient
    from model.services.ports import EmbeddingPort, EventLogStore, EventRepository, ScenarioRepository

_logger = logging.getLogger("eventhorizon.play_turn")


def _looks_like_gibberish(text: str) -> bool:
    """LiveContentAuthor 调用前的廉价本地兜底：GLM 配的小模型（glm-4-flash）就算
    prompt 里明确要求"说不通就拒绝"，实测对着纯乱码（"asdkjhaskjdh"这种）也会
    硬编一个场景出来，不肯拒绝——提示词管不住的部分，先在本地挡一层最明显的：
    一个汉字都没有，基本不可能是有意义的游戏内动作描述。不追求完美（"合理但
    无意义的中文"这类还是会被模型编出东西来，是用户已经知情接受的代价，见
    README §1.12 的 LiveContentAuthor 例外说明），只挡最便宜能挡住的那一档。"""
    return not any("一" <= ch <= "鿿" for ch in text)

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
        embedding: "EmbeddingPort | None" = None,
        narrative_writer: "LlmClient | None" = None,
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
        # embedding/narrative_writer 都是可选的（未配置就是 None）：embedding 只用于
        # predicate_text 的向量相似度判定；narrative_writer 是 LlmEventWriter（README
        # 对局第二段表格），事件命中但 variants 为空时现场补一句文案，见
        # _ensure_variants()。README 5.3 对局隔离针对的是"录入侧大模型草稿生成"那个
        # 端口，不是这两个——V2 向量匹配/LlmEventWriter 本来就该在对局路径里用。
        # LiveContentAuthor 复用同一个 narrative_writer 客户端（同一个 LlmClient
        # Protocol），是解析彻底失败（规则 + 向量都没匹配上）时的最后一层兜底，
        # 见 handle_player_text/_handle_move——README §1.12 的一次有意识例外，
        # 用户已明确要求，见 live_content_author.py 顶部说明。
        self._live_content_author = LiveContentAuthor(narrative_writer) if narrative_writer is not None else None
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
        text = generate_live_variant_text(self.narrative_writer, defn.event_id, defn.tags)
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

        # 1.5) 追问补全——LiveContentAuthor 上一句判断信息不全时挂起等这一句
        # （README §1.12 LiveContentAuthor 例外，最多追问 3 次，见 _resolve_clarification）。
        if agent.pending_clarification is not None:
            return self._resolve_clarification(agent, world, raw)

        # 2) 常规命令：规则解析器 -> 向量意图兜底 -> 实时大模型创作，三层依次尝试
        cmd = self.parser.parse(raw, agent.scene_focus)
        if cmd is None:
            cmd = self._match_command_by_intent(raw, agent)
        if cmd is None:
            outcome = self._author_live_command(agent, raw)
            resolved = self._resolve_command_outcome(agent, outcome, raw, prior_attempts=0)
            if isinstance(resolved, TurnResult):
                return resolved
            cmd = resolved
        if cmd is None:
            return TurnResult.parse_failed(self._soft_guidance_message(agent, world))
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
            return TurnResult.parse_failed(self._soft_guidance_message(agent, world))
        defn = self._ensure_variants(defn)
        occ = self._new_occurrence(agent, defn, TriggerSource.PLAYER)
        return self.execute_occurrence(agent, world, occ, defn) or TurnResult.rejected("现在做不了这个。")

    def _set_pending_clarification(self, agent: "Agent", original_text: str, kind: str, attempts: int) -> None:
        from model.domain.agent import PendingClarification

        apply_agent_diff(agent, AppliedDiff(
            pending_clarification_set=PendingClarification(original_text=original_text, kind=kind, attempts=attempts)
        ))

    def _clear_pending_clarification(self, agent: "Agent") -> None:
        if agent.pending_clarification is not None:
            apply_agent_diff(agent, AppliedDiff(pending_clarification_set=None))

    def _resolve_clarification(self, agent: "Agent", world: "WorldView", raw: str) -> TurnResult:
        """追问回来的这句话，跟玩家最初那句拼在一起重新尝试创作——不重新走规则
        解析/向量兜底（那两层已经在第一次就试过判定不了了），直接回到失败的那
        一层继续。成不成、要不要再问一次，都由 _resolve_command_outcome/
        _resolve_location_outcome 统一处理（这两个函数在这里和"第一次就失败"
        两条路径上共用，是同一套 3 次上限逻辑）。"""
        pending = agent.pending_clarification
        combined = f"{pending.original_text}（补充：{raw}）"
        if pending.kind == "command":
            outcome = self._author_live_command(agent, combined)
            resolved = self._resolve_command_outcome(agent, outcome, combined, pending.attempts)
            if isinstance(resolved, TurnResult):
                return resolved
            if resolved is None:
                return TurnResult.parse_failed(self._soft_guidance_message(agent, world))
            return self._dispatch_command(agent, world, resolved)
        outcome = self._author_live_destination_outcome(agent, world, combined)
        resolved = self._resolve_location_outcome(agent, world, outcome, combined, pending.attempts)
        if isinstance(resolved, TurnResult):
            return resolved
        if resolved is None:
            return TurnResult.rejected(f"找不到「{combined}」这个地方。")
        return self._complete_move(agent, world, resolved)

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

    def _author_live_command(self, agent: "Agent", raw: str) -> LiveAuthorOutcome:
        """规则解析 + 向量兜底都没命中——最后一层：实时调大模型判断这句话该
        怎么办（LiveContentAuthor，README §1.12 的有意识例外，见
        live_content_author.py 顶部说明）。没配置大模型/一个汉字都没有的纯乱码
        直接判 reject，不走到大模型那一步（见 _looks_like_gibberish 的说明）。"""
        if self._live_content_author is None or _looks_like_gibberish(raw):
            return LiveAuthorOutcome(kind="reject")
        return self._live_content_author.author_command_event(raw, agent.location_type)

    def _resolve_command_outcome(
        self, agent: "Agent", outcome: LiveAuthorOutcome, original_text: str, prior_attempts: int
    ) -> "ParsedCommand | TurnResult | None":
        """把 LiveAuthorOutcome 的三态落地：needs_clarification 挂起追问（最多真的
        问出 3 次，第 4 次评估时还不够就放弃——attempts 记的是"已经问出去几次"，
        不是"已经失败几次"，超过 3 才放弃，不是到 3 就放弃）、reject 交回调用方
        原有的"听不懂"文案（返回 None）、ready 才真的校验+落库+返回可执行的
        ParsedCommand。"""
        if outcome.kind == "needs_clarification" and outcome.question:
            attempts = prior_attempts + 1
            if attempts > 3:
                self._clear_pending_clarification(agent)
                return None
            self._set_pending_clarification(agent, original_text, "command", attempts)
            return TurnResult(freeform_narrative=outcome.question)
        self._clear_pending_clarification(agent)
        if outcome.kind != "ready" or outcome.command_raw is None:
            return None
        event_id = "live_" + uuid.uuid4().hex[:10]
        raw_event = {
            **outcome.command_raw,
            "event_id": event_id,
            "applicable_locations": [agent.location_type],
            "predicate": None,
            "aliases": list(dict.fromkeys([*outcome.command_raw.get("aliases", []), original_text.strip()])),
            # LiveContentAuthor 的 variants 是纯字符串列表，validate_event_def
            # 要的是 {"text":..., "weight":...} 字典——跟 admin_controller.py::
            # generate_events 里同样的转换。
            "variants": [{"text": text, "weight": 1.0} for text in outcome.command_raw.get("variants", [])],
            "is_draft": False,
            "is_command": True,
            # 实时创作没有专门的描述字段——管理员事后在编辑器里翻到这条 live_
            # 开头的事件时，总不能只看到一个 id，拿第一条变体文案顶上。
            "description": (outcome.command_raw.get("variants") or [""])[0],
        }
        # load_event_defs(None) 不是 list_all()：list_all() 明确标注"只供录入编辑器
        # 用，对局路径必须走 load_event_defs()"（草稿会被过滤掉），这里虽然只是拿
        # id 集合做联动校验，也不该破例。
        catalog = ValidationCatalog(known_event_ids={e.event_id for e in self.events.load_event_defs(None)})
        defn, errors = validate_event_def(raw_event, catalog)
        if defn is None:
            _logger.warning("实时创作的事件没通过校验：%s", errors)
            return None
        # 跟 admin_controller.py::save_event 同样的 narrative_embedding 计算方式
        # （tags+aliases+variants 拼接），不然这条实时创作的事件以后碰到相似但不
        # 完全相同的措辞时，_match_command_by_intent 的向量兜底找不到它。
        narrative_text = " ".join(
            list(raw_event.get("tags") or [])
            + list(raw_event.get("aliases") or [])
            + [v["text"] for v in raw_event.get("variants") or []]
        ).strip()
        if narrative_text:
            defn = replace(defn, narrative_embedding=embed_safely(self.embedding, narrative_text))
        self.events.save_event_def(defn)
        return ParsedCommand(event_id=defn.event_id, location_hint=None, target=None, args={})

    # ---------- 系统命令：move / retreat_start（GAME_DESIGN §3.1，非库内事件）----------
    def _handle_move(self, agent: "Agent", world: "WorldView", cmd) -> TurnResult:
        if agent.state.name != "idle":
            return TurnResult.rejected("现在走不开。")
        destination = world.find_location_by_name(cmd.location_hint) if cmd.location_hint else None
        if destination is None and cmd.location_hint:
            outcome = self._author_live_destination_outcome(agent, world, cmd.location_hint)
            resolved = self._resolve_location_outcome(agent, world, outcome, cmd.location_hint, prior_attempts=0)
            if isinstance(resolved, TurnResult):
                return resolved
            destination = resolved
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

    def _list_visible_locations(self, world: "WorldView") -> list[dict]:
        """给 LiveContentAuthor 的 list_locations 工具用（真正的 function calling，
        见 live_content_author.py/llm_tool_loop.py）——只列玩家看得到的地点，
        隐藏未发现的不给：不能让模型拿神识扫描都没发现的秘境当"已有地点"回答
        玩家，跟 WorldView.find_location_by_name 的可见性规则一致。"""
        state = world.mutable_state()
        return [
            {"location_id": loc.location_id, "name": loc.name, "location_type": loc.location_type}
            for loc in state.locations.values()
            if not loc.hidden or loc.discovered
        ]

    def _author_live_destination_outcome(self, agent: "Agent", world: "WorldView", hint: str) -> LiveAuthorOutcome:
        """`find_location_by_name` 找不到目的地时的最后一层兜底——实时创作一个新
        地点（LiveContentAuthor，README §1.12 的有意识例外，见 live_content_author.py
        顶部说明），带 list_locations 工具查真实地点数据。"""
        if self._live_content_author is None or _looks_like_gibberish(hint):
            return LiveAuthorOutcome(kind="reject")
        current_name = world.name_of(agent.location_id)
        current_type = world.location_type_of(agent.location_id)
        return self._live_content_author.author_location(
            hint, current_name, current_type, lambda: self._list_visible_locations(world)
        )

    def _resolve_location_outcome(
        self, agent: "Agent", world: "WorldView", outcome: LiveAuthorOutcome, original_text: str, prior_attempts: int
    ) -> "Location | TurnResult | None":
        """把 LiveAuthorOutcome 的三态（外加"其实是已有地点"这个第四种情况）落地：
        needs_clarification 挂起追问（满 3 次放弃，回落"找不到"）；reject 返回
        None 交回调用方原有的"找不到"文案；ready 时——`existing_location_id` 命中
        就直接返回那个已有 Location（不新建）；否则按 is_internal 新建子地点
        （+ 一条连回当前地点的 Route，当场可达）或新建隐藏地点（不移动、告知
        "尚未对外开放"）。

        新地点/新路线直接写进 `world.mutable_state()`——不需要额外接线持久化：
        `world` 是 ChatController 每回合传进来的同一个引用，回合结束后
        ChatController 本来就会无条件 `world_repo.save(...)`（chat_controller.py），
        这里改了内存里的 WorldState，会跟着这次回合一起整份存盘。"""
        if outcome.kind == "needs_clarification" and outcome.question:
            attempts = prior_attempts + 1  # 已经问出去几次，超过 3 才放弃（见 _resolve_command_outcome 的同款注释）
            if attempts > 3:
                self._clear_pending_clarification(agent)
                return None
            self._set_pending_clarification(agent, original_text, "location", attempts)
            return TurnResult(freeform_narrative=outcome.question)
        self._clear_pending_clarification(agent)
        if outcome.kind != "ready":
            return None
        state = world.mutable_state()
        if outcome.existing_location_id:
            return state.locations.get(outcome.existing_location_id)
        if outcome.location_decision is None:
            return None
        from model.domain.map import Location, LocationKind, Route

        decision = outcome.location_decision
        current = state.get(agent.location_id)
        new_id = "loc_" + uuid.uuid4().hex[:10]
        if decision.is_internal:
            parent_id = current.parent_location_id if current is not None and current.parent_location_id else agent.location_id
            new_location = Location(
                location_id=new_id, name=decision.name, kind=LocationKind(decision.kind),
                location_type=decision.location_type, parent_location_id=parent_id, hidden=False, discovered=True,
            )
            state.locations[new_id] = new_location
            state.routes.append(Route(from_id=agent.location_id, to_id=new_id, bidirectional=True))
            return new_location
        new_location = Location(
            location_id=new_id, name=decision.name, kind=LocationKind(decision.kind),
            location_type=decision.location_type, parent_location_id=None, hidden=True, discovered=False,
        )
        state.locations[new_id] = new_location
        return TurnResult.rejected(f"「{decision.name}」虽有耳闻，但眼下尚未对外开放，暂时去不了。")

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
        pending_def = self._ensure_variants(pending_def)
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
        synthetic = replace(host_def, result_pool=next_node.results, predicate=None, reply_options=())
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


def default_move_def() -> "GameEventDef":
    """content 侧没有注册 event_id="move" 的兜底（GAME_DESIGN §3.1："去{地点}"是
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
