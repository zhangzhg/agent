"""model/services/live_authoring_coordinator.py — LiveContentAuthor 在对局里的
落地编排（README §1.12～§1.16）。

`LiveContentAuthor`（live_content_author.py）只管"问模型、把回答解析成结构化
结果"，不碰游戏状态；这一层负责把它的 `LiveAuthorOutcome` 真正落到对局里：校验、
落库、算向量、挂追问、记延迟结果、回收旧的实时事件。

**为什么单独成一层**（优化建议.md P1-1）：这一摊逻辑原本全长在
`PlayTurnService` 里，把它顶到了 850 行——一个类同时管输入路由、5 种挂起态、
实时创作、系统命令、两段式结算、流程图推进。这些方法彼此高度内聚（都围绕
"LiveContentAuthor 说了什么、该怎么落地"），跟两段式流水线基本不耦合，是最干净
的一条切割线。`PlayTurnService` 保留门面职责，按需委派到这里。

**这里是对局路径上所有大模型调用的唯一入口**，所以每回合的调用预算
（`LlmCallBudget`）也在这一层收口——见 `begin_turn()`。
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Callable, Literal

from model.domain.diff import AppliedDiff, apply_agent_diff
from model.domain.events import LIVE_EVENT_ID_PREFIX
from model.services.event_validation import ValidationCatalog, validate_event_def
from model.services.game_context_tools import list_all_locations
from model.services.live_content_author import LiveAuthorOutcome, LiveContentAuthor
from model.services.matching import embed_safely
from model.services.turn_result import TurnResult

if TYPE_CHECKING:
    from model.domain.agent import Agent
    from model.domain.map import Location, WorldView
    from model.services.chat_parser import ParsedCommand
    from model.services.live_narrative_writer import LlmClient
    from model.services.ports import EmbeddingPort, EventRepository

_logger = logging.getLogger("eventhorizon.live_authoring")

# 追问上限：最多真的问出 3 次。attempts 记的是"已经问出去几次"，不是"已经失败
# 几次"，所以判据是"超过 3 才放弃"而不是"到 3 就放弃"——差一个 off-by-one 就会
# 变成只问 2 次。
_MAX_CLARIFICATION_ATTEMPTS = 3

# PendingLiveResult 每轮问一次"故事线是否收尾"，连问这么多轮都没结果就强制落地。
# 理由跟追问上限一样：不能让玩家没兴趣接话就把一个伏笔永远悬在那儿、顺带把
# "未结束不能抽下一个奇遇"的限制锁死。
_LIVE_RESULT_MAX_WAIT_TURNS = 3

# 实时创作事件（live_ 前缀）的保有上限，超出就删最老的。每一句没被识别的玩家输入
# 都会创作一条永久事件，不回收的话：录入编辑器的事件列表会被玩家碎碎念淹没，向量
# 兜底每回合装载的命令池也越滚越大。手工/种子内容不在回收范围内。
_LIVE_EVENT_KEEP = 200

# 单回合的大模型调用预算（优化建议.md P1-4）。一次玩家输入最坏情况下会串行发起
# 多次往返：伏笔收尾判断 → 实时创作 → result_pool 补问 → 地点创作的工具循环 →
# 补叙事文案。全部同步阻塞，一旦某次 GLM 变慢，玩家就是干等且看不出卡在哪。
# 超预算就直接走各调用点已经写好的降级路径（reject / 默认值 / 兜底文案），
# 不额外发明新的失败形态。
_MAX_LLM_CALLS_PER_TURN = 6
_MAX_LLM_SECONDS_PER_TURN = 45.0


@dataclass(frozen=True, slots=True)
class Resolution:
    """`resolve_*_outcome` 的三态结果（优化建议.md P2）。

    以前这两个方法的返回类型是 `ParsedCommand | TurnResult | None` /
    `Location | TurnResult | None`——三种含义挤在一个联合类型里，逼得每个调用点都
    先 `isinstance(x, TurnResult)` 分一次支，再拿 `None` 当第三种情况，读的人得先
    想清楚"None 到底是失败还是没有值"。三态说清楚就不用猜了：

    - `ready(value)`：拿到了可执行的东西（ParsedCommand / Location），继续往下走。
    - `replied(turn_result)`：这一轮已经有答复了（追问、或"去不了"之类），直接返回它。
    - `failed()`：没成，调用方回落自己的兜底文案。
    """

    kind: Literal["ready", "replied", "failed"]
    value: object | None = None
    reply: "TurnResult | None" = None

    @staticmethod
    def ready(value: object) -> "Resolution":
        return Resolution(kind="ready", value=value)

    @staticmethod
    def replied(turn_result: "TurnResult") -> "Resolution":
        return Resolution(kind="replied", reply=turn_result)

    @staticmethod
    def failed() -> "Resolution":
        return Resolution(kind="failed")


@dataclass
class LlmCallBudget:
    """一次玩家输入之内的大模型调用预算。用完就"假装模型不可用"，让调用方走它
    本来就有的降级分支——这是本项目一贯的做法（embed_safely 的空向量、
    LiveAuthorOutcome 的 reject），不引入新的异常类型。"""

    max_calls: int = _MAX_LLM_CALLS_PER_TURN
    max_seconds: float = _MAX_LLM_SECONDS_PER_TURN
    calls_used: int = 0
    started_at: float = 0.0

    def start(self) -> None:
        self.calls_used = 0
        self.started_at = time.monotonic()

    def exhausted(self) -> bool:
        if self.calls_used >= self.max_calls:
            _logger.warning("本回合大模型调用次数已达上限 %d，后续调用走降级路径", self.max_calls)
            return True
        if self.started_at and (time.monotonic() - self.started_at) > self.max_seconds:
            _logger.warning("本回合大模型耗时已超 %.0f 秒，后续调用走降级路径", self.max_seconds)
            return True
        return False

    def consume(self) -> None:
        self.calls_used += 1


class _BudgetedClient:
    """把预算钳在真实 LlmClient 外面——`LiveContentAuthor` 内部有好几处调用
    （创作、补问 result_pool、收尾判断、工具循环的多轮往返），逐个去改调用点既
    啰嗦又容易漏，不如在客户端这一层统一收口。

    预算耗尽时抛 RuntimeError：`LiveContentAuthor` 的每个方法本来就把客户端异常
    当"这次没成"处理（各自 try/except 后返回 reject/空结果），所以这里不需要
    它配合改动，降级路径是现成的。"""

    def __init__(self, inner: "LlmClient", budget: LlmCallBudget) -> None:
        self._inner = inner
        self._budget = budget

    def complete(self, prompt: str) -> str:
        if self._budget.exhausted():
            raise RuntimeError("本回合大模型调用预算已用尽")
        self._budget.consume()
        return self._inner.complete(prompt)

    def complete_with_tools(self, messages: list[dict], tools: list[dict]) -> dict:
        if self._budget.exhausted():
            raise RuntimeError("本回合大模型调用预算已用尽")
        self._budget.consume()
        return self._inner.complete_with_tools(messages, tools)


class LiveAuthoringCoordinator:
    """把 LiveAuthorOutcome 落到对局状态上。不持有跨回合状态：预算对象每回合由
    `begin_turn()` 重置，其余全部读写 Agent/World 自身。"""

    def __init__(
        self,
        events: "EventRepository",
        narrative_writer: "LlmClient | None",
        embedding: "EmbeddingPort | None" = None,
    ) -> None:
        self.events = events
        self.embedding = embedding
        self._budget = LlmCallBudget()
        self._author = (
            LiveContentAuthor(_BudgetedClient(narrative_writer, self._budget))
            if narrative_writer is not None
            else None
        )

    @property
    def enabled(self) -> bool:
        return self._author is not None

    def begin_turn(self) -> None:
        """每次玩家输入开始时调一次，重置这一回合的大模型调用预算。"""
        self._budget.start()

    # ---------- 命令创作 ----------
    def author_command(self, agent: "Agent", raw: str) -> LiveAuthorOutcome:
        """规则解析 + 向量兜底都没命中的最后一层。没配大模型、或一个汉字都没有的
        纯乱码，直接判 reject 不走到模型那一步（见 looks_like_gibberish）。"""
        if self._author is None or looks_like_gibberish(raw):
            return LiveAuthorOutcome(kind="reject")
        return self._author.author_command_event(raw, agent.location_type)

    def resolve_command_outcome(
        self, agent: "Agent", outcome: LiveAuthorOutcome, original_text: str, prior_attempts: int
    ) -> Resolution:
        """三态落地：needs_clarification 挂起追问、reject 返回 None 交回调用方的
        兜底文案、ready 才校验+落库+返回可执行的 ParsedCommand。"""
        from model.services.chat_parser import ParsedCommand

        pending = self._handle_clarification(agent, outcome, original_text, "command", prior_attempts)
        if pending is not _NOT_CLARIFICATION:
            return pending
        if outcome.kind != "ready" or outcome.command_raw is None:
            return Resolution.failed()

        defn = self._build_and_save_event(agent, outcome, original_text)
        if defn is None:
            return Resolution.failed()
        self._remember_deferred_result(agent, outcome, defn.event_id)
        self._prune_live_events(agent, just_created=defn.event_id)
        return Resolution.ready(ParsedCommand(event_id=defn.event_id, location_hint=None, target=None, args={}))

    def _build_and_save_event(self, agent: "Agent", outcome: LiveAuthorOutcome, original_text: str):
        event_id = LIVE_EVENT_ID_PREFIX + uuid.uuid4().hex[:10]
        raw_event = {
            **outcome.command_raw,
            "event_id": event_id,
            "applicable_locations": [agent.location_type],
            "predicate": None,
            "aliases": list(dict.fromkeys([*outcome.command_raw.get("aliases", []), original_text.strip()])),
            # LiveContentAuthor 的 variants 是纯字符串列表，validate_event_def 要的是
            # {"text":..., "weight":...} 字典——跟 admin_controller.py::generate_events
            # 里同样的转换。
            "variants": [{"text": text, "weight": 1.0} for text in outcome.command_raw.get("variants", [])],
            "is_draft": False,
            "is_command": True,
            # 实时创作没有专门的描述字段——管理员事后在编辑器里翻到这条 live_ 开头的
            # 事件时，总不能只看到一个 id，拿第一条变体文案顶上。
            "description": (outcome.command_raw.get("variants") or [""])[0],
        }
        # 只要 id 集合，走 published_event_ids() 而不是 load_event_defs(None)——后者会把
        # 整个事件库反序列化一遍，而这里每处理一句没听懂的话就要来一次。语义不变：
        # 同样只认已发布事件，不含草稿。
        catalog = ValidationCatalog(known_event_ids=self.events.published_event_ids())
        defn, errors = validate_event_def(raw_event, catalog)
        if defn is None:
            _logger.warning("实时创作的事件没通过校验：%s", errors)
            return None
        # 跟 admin_controller.py::save_event 同样的 narrative_embedding 计算方式
        # （tags+aliases+variants 拼接），不然这条事件以后碰到相似但不完全相同的
        # 措辞时，向量兜底找不到它。
        narrative_text = " ".join(
            list(raw_event.get("tags") or [])
            + list(raw_event.get("aliases") or [])
            + [v["text"] for v in raw_event.get("variants") or []]
        ).strip()
        if narrative_text:
            defn = replace(defn, narrative_embedding=embed_safely(self.embedding, narrative_text))
        self.events.save_event_def(defn)
        return defn

    # ---------- 地点创作 ----------
    def author_destination(self, agent: "Agent", world: "WorldView", hint: str) -> LiveAuthorOutcome:
        """`find_location_by_name` 找不到目的地时的最后一层兜底。带 list_locations
        工具查真实地点数据（game_context_tools.py::list_all_locations 的可见性过滤
        跟这里要的完全一样，直接复用）。"""
        if self._author is None or looks_like_gibberish(hint):
            return LiveAuthorOutcome(kind="reject")
        return self._author.author_location(
            hint, world.name_of(agent.location_id), world.location_type_of(agent.location_id),
            lambda: list_all_locations(world),
        )

    def resolve_location_outcome(
        self, agent: "Agent", world: "WorldView", outcome: LiveAuthorOutcome, original_text: str, prior_attempts: int
    ) -> Resolution:
        """三态 + "其实是已有地点"这个第四种情况。ready 时：`existing_location_id`
        命中就直接返回那个已有 Location（不新建）；否则按 is_internal 新建子地点
        （+ 一条连回当前地点的 Route，当场可达）或新建隐藏地点（不移动、告知
        "尚未对外开放"）。

        新地点/新路线直接写进 `world.mutable_state()`——不需要额外接线持久化：
        world 是 ChatController 每回合传进来的同一个引用，回合结束后 ChatController
        本来就会 world_repo.save(...)，这里改的内存状态会跟着一起存盘。"""
        pending = self._handle_clarification(agent, outcome, original_text, "location", prior_attempts)
        if pending is not _NOT_CLARIFICATION:
            return pending
        if outcome.kind != "ready":
            return Resolution.failed()

        state = world.mutable_state()
        if outcome.existing_location_id:
            existing = state.locations.get(outcome.existing_location_id)
            return Resolution.ready(existing) if existing is not None else Resolution.failed()
        if outcome.location_decision is None:
            return Resolution.failed()

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
            return Resolution.ready(new_location)
        new_location = Location(
            location_id=new_id, name=decision.name, kind=LocationKind(decision.kind),
            location_type=decision.location_type, parent_location_id=None, hidden=True, discovered=False,
        )
        state.locations[new_id] = new_location
        return Resolution.replied(
            TurnResult.rejected(f"「{decision.name}」虽有耳闻，但眼下尚未对外开放，暂时去不了。")
        )

    # ---------- 追问挂起态 ----------
    def _handle_clarification(
        self, agent: "Agent", outcome: LiveAuthorOutcome, original_text: str, kind: str, prior_attempts: int
    ):
        """命令/地点两条路径共用同一套追问上限逻辑。返回 `_NOT_CLARIFICATION`
        表示"这不是追问分支，调用方继续按自己的方式处理 outcome"——用哨兵而不是
        None，因为 None 在两个调用方那里都是有意义的返回值（"放弃，走兜底文案"）。"""
        if outcome.kind == "needs_clarification" and outcome.question:
            attempts = prior_attempts + 1
            if attempts > _MAX_CLARIFICATION_ATTEMPTS:
                self.clear_clarification(agent)
                return Resolution.failed()
            apply_agent_diff(agent, AppliedDiff(pending_clarification_set=_new_clarification(
                original_text=original_text, kind=kind, attempts=attempts
            )))
            return Resolution.replied(TurnResult(freeform_narrative=outcome.question))
        self.clear_clarification(agent)
        return _NOT_CLARIFICATION

    def clear_clarification(self, agent: "Agent") -> None:
        if agent.pending_clarification is not None:
            apply_agent_diff(agent, AppliedDiff(pending_clarification_set=None))

    # ---------- 延迟结果（PendingLiveResult）----------
    def _remember_deferred_result(self, agent: "Agent", outcome: LiveAuthorOutcome, event_id: str) -> None:
        """这个动作留了一个"当下还没兑现"的另一面影响——记下事件 id + 待触发结果，
        等下一轮判断"故事线是否收尾"后再落地。绝大多数事件没有这部分。"""
        deferred_pool = outcome.command_raw.get("deferred_result_pool") or []
        if not deferred_pool:
            return
        from model.domain.agent import PendingLiveResult

        apply_agent_diff(agent, AppliedDiff(pending_live_result_set=PendingLiveResult(
            event_id=event_id,
            deferred_result_pool=tuple(deferred_pool),
            narrative_hint=(outcome.command_raw.get("variants") or [""])[0],
        )))

    def maybe_conclude_deferred_result(self, agent: "Agent", raw: str) -> None:
        """每轮问一次"玩家这句话算不算把伏笔翻篇了"：算，就把攒着的 state_change
        一次性落地、清挂起态（同时解除"未结束不能抽下一个奇遇"的限制）；连问
        _LIVE_RESULT_MAX_WAIT_TURNS 轮都没收尾（或压根没配大模型没法判断），也强制
        落地。纯副作用，不吃掉 raw——这句话接下来还要被正常解析。"""
        pending = agent.pending_live_result
        if pending is None:
            return
        concluded = False
        if self._author is not None:
            concluded = self._author.check_storyline_concluded(pending.narrative_hint, raw)
        attempts = pending.attempts + 1
        if not concluded and attempts <= _LIVE_RESULT_MAX_WAIT_TURNS:
            apply_agent_diff(agent, AppliedDiff(pending_live_result_set=replace(pending, attempts=attempts)))
            return
        attr_deltas = tuple((item["field"], item["delta"]) for item in pending.deferred_result_pool)
        apply_agent_diff(agent, AppliedDiff(attr_deltas=attr_deltas, pending_live_result_set=None))

    # ---------- 容量回收 ----------
    def _prune_live_events(self, agent: "Agent", just_created: str) -> None:
        """每创作一条就顺手回收一次。受保护的 id 必须排除，否则会留下悬空引用：
        玩家正挂着等回复的分支事件、还没结算的延迟结果、流程图宿主事件，以及刚
        创建、马上就要执行的这一条。"""
        protected = {just_created}
        if agent.pending_encounter_id:
            protected.add(agent.pending_encounter_id)
        if agent.pending_live_result is not None:
            protected.add(agent.pending_live_result.event_id)
        if agent.pending_scenario is not None:
            protected.add(agent.pending_scenario.host_event_id)
        removed = self.events.prune_live_events(_LIVE_EVENT_KEEP, protected_ids=protected)
        if removed:
            _logger.info("回收了 %d 条实时创作的旧事件（上限 %d）", removed, _LIVE_EVENT_KEEP)


class _NotClarification:
    """`_handle_clarification` 的"不是这个分支"哨兵，不用 None（None 有别的含义）。"""

    def __repr__(self) -> str:  # pragma: no cover - 只为调试可读
        return "<NOT_CLARIFICATION>"


_NOT_CLARIFICATION = _NotClarification()


def _new_clarification(original_text: str, kind: str, attempts: int):
    from model.domain.agent import PendingClarification

    return PendingClarification(original_text=original_text, kind=kind, attempts=attempts)


def looks_like_gibberish(text: str) -> bool:
    """调模型之前的廉价本地兜底：GLM 配的小模型（glm-4-flash）就算 prompt 里明确
    要求"说不通就拒绝"，实测对着纯乱码（"asdkjhaskjdh"这种）也会硬编一个场景出来，
    不肯拒绝——提示词管不住的部分，先在本地挡一层最明显的：一个汉字都没有，基本
    不可能是有意义的游戏内动作描述。不追求完美（"合理但无意义的中文"这类还是会被
    模型编出东西来，是用户已经知情接受的代价，见 README §1.12），只挡最便宜能挡住
    的那一档。"""
    return not any("一" <= ch <= "鿿" for ch in text)
