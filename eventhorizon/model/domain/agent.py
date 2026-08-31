"""model/domain/agent.py — Agent、物品背包挂起态、事件历史（对应 README 2.4 / 1.4.3 / 1.6）。"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from model.domain.balance import DEFAULT_REALM_ORDER
from model.domain.items import Inventory
from model.domain.predicates import EvalContext
from model.domain.time import AgentTimeAnchor, GameTime

if TYPE_CHECKING:
    from model.domain.cause import CauseLink
    from model.domain.map import WorldView
    from model.domain.states import AgentState


@dataclass(frozen=True, slots=True)
class PendingScenario:
    """流程图跨回合进度。存在 Agent 上而非 ScenarioExecutor 里，才能进快照。"""

    scenario_id: str
    current_node_id: str
    host_event_id: str


@dataclass(slots=True)
class BiographyEntry:
    at: GameTime
    text: str
    event_id: str | None = None


@dataclass(slots=True)
class Biography:
    """NPC 生平履历（对应 README 1.5.1）：以事件流形式存储，非全量文本，按需懒加载。"""

    entries: list[BiographyEntry] = field(default_factory=list)

    def append(self, at: GameTime, text: str, event_id: str | None = None) -> None:
        self.entries.append(BiographyEntry(at, text, event_id))

    def epitaph(self) -> str:
        """死亡结算生成"生平碑文"（README 2.5）：把履历条目连成一段文字。"""
        return "；".join(e.text for e in self.entries) or "生平寂寂，未有可记之事。"


@dataclass(slots=True)
class AgentEventHistory:
    """粗筛与新鲜度的唯一数据源。随 Agent 存档，不是缓存。

    recency_factor 按"次数推移"而非墙钟/游戏钟计算：内部维护一个随每次 record()
    递增的序号，距上次触发经过的序号差驱动指数恢复曲线——这样调用方（matching.py）
    不需要额外传入 now，接口与 README 1.4.3 描述的签名一致。
    """

    triggers: dict[str, list[GameTime]] = field(default_factory=dict)  # event_id → 触发时刻（按窗口截断）
    variant_cursor: dict[str, int] = field(default_factory=dict)  # event_id → 上次用过的变体下标
    recent_tags: list[tuple[str, GameTime]] = field(default_factory=list)  # 标签滚动窗口，供配额补偿
    exclusive_tag_expiry: dict[str, GameTime] = field(default_factory=dict)  # tag → 互斥屏蔽截止时刻
    last_trigger_seq: dict[str, int] = field(default_factory=dict)  # event_id → 触发时的全局序号
    _sequence: int = 0

    MAX_TRIGGERS_PER_EVENT = 64  # TODO #2：先按定长截断，V1 视实际冷却时长调整
    TAG_QUOTA_WINDOW = 50
    TAG_QUOTA_STRENGTH = 1.5
    RECENCY_HALF_LIFE_STEPS = 8
    RECENCY_FLOOR = 0.2

    # —— 粗筛用（硬过滤，README 1.4.2）——
    def in_cooldown(self, event_id: str, now: GameTime, cooldown_shichen: int) -> bool:
        history = self.triggers.get(event_id)
        if not history or cooldown_shichen <= 0:
            return False
        last = history[-1]
        return now < last.add_shichen(cooldown_shichen)

    def trigger_count(self, event_id: str) -> int:
        return len(self.triggers.get(event_id, ()))

    def active_exclusive_tags(self, now: GameTime) -> set[str]:
        return {tag for tag, until in self.exclusive_tag_expiry.items() if now < until}

    # —— 重排用（软乘子，README 1.4.3）——
    def recency_factor(self, event_id: str, curve: dict | None = None) -> float:
        """距上次触发越近权重越低，随后续触发次数推移渐进恢复到 1（比 0/1 冷却更细腻）。"""
        last_seq = self.last_trigger_seq.get(event_id)
        if last_seq is None:
            return 1.0
        curve = curve or {}
        half_life = curve.get("half_life_steps", self.RECENCY_HALF_LIFE_STEPS)
        floor = curve.get("floor", self.RECENCY_FLOOR)
        steps_since = max(0, self._sequence - last_seq)
        recovered = 1.0 - 0.5 ** (steps_since / half_life) if half_life > 0 else 1.0
        return floor + (1.0 - floor) * recovered

    def tag_quota_factor(self, tags: tuple[str, ...]) -> float:
        if not tags or not self.recent_tags:
            return 1.0
        window = self.recent_tags[-self.TAG_QUOTA_WINDOW:]
        counts = Counter(t for t, _ in window)
        total = len(window)
        distinct = len(counts) or 1
        fair_share = 1.0 / distinct
        factors = []
        for tag in tags:
            share = counts.get(tag, 0) / total
            deficit = max(0.0, fair_share - share)
            factors.append(1.0 + deficit * self.TAG_QUOTA_STRENGTH)
        return sum(factors) / len(factors)

    # —— 变体轮换（README 1.4.3 文案变体）——
    def last_variant(self, event_id: str) -> int | None:
        return self.variant_cursor.get(event_id)

    def record(
        self,
        event_id: str,
        at: GameTime,
        tags: tuple[str, ...],
        variant: int,
        exclusive_tags: tuple[str, ...] = (),
        cooldown_shichen: int = 0,
    ) -> None:
        bucket = self.triggers.setdefault(event_id, [])
        bucket.append(at)
        if len(bucket) > self.MAX_TRIGGERS_PER_EVENT:
            del bucket[: len(bucket) - self.MAX_TRIGGERS_PER_EVENT]
        self.variant_cursor[event_id] = variant
        self._sequence += 1
        self.last_trigger_seq[event_id] = self._sequence
        for tag in tags:
            self.recent_tags.append((tag, at))
        if len(self.recent_tags) > self.TAG_QUOTA_WINDOW * 4:
            del self.recent_tags[: len(self.recent_tags) - self.TAG_QUOTA_WINDOW * 4]
        if exclusive_tags and cooldown_shichen > 0:
            until = at.add_shichen(cooldown_shichen)
            for tag in exclusive_tags:
                self.exclusive_tag_expiry[tag] = until


class _AgentEvalContext:
    """Agent.as_eval_context() 的具体实现：把 Agent + WorldView 适配成 EvalContext。"""

    def __init__(self, agent: "Agent", world: "WorldView | None") -> None:
        self._agent = agent
        self._world = world

    def attr(self, name: str) -> float:
        return float(getattr(self._agent, name, 0))

    def realm_rank(self) -> int:
        if self._agent.realm in DEFAULT_REALM_ORDER:
            return DEFAULT_REALM_ORDER.index(self._agent.realm)
        return -1

    def money(self) -> int:
        return self._agent.money

    def age(self) -> int:
        return self._agent.age

    def has_item(self, item_id: str) -> bool:
        return self._agent.inventory.has(item_id)

    def flag(self, name: str) -> bool:
        return name in self._agent.flags

    def location_type(self) -> str:
        return self._agent.location_type

    def has_cause(self, tag: str, target: str) -> bool:
        return any(c.tag == tag and c.target == target for c in self._agent.causes)


@dataclass(slots=True)
class Agent:
    agent_id: str
    location_id: str
    location_type: str
    age: int
    realm: str
    money: int
    satiety: int
    cultivation: float
    heart_demon: float
    lifespan_left: float  # 寿元，闭关按结算跨度扣（README 2.4）
    flags: set[str]
    inventory: Inventory
    time_anchor: AgentTimeAnchor
    event_history: AgentEventHistory
    state: "AgentState"
    causes: list["CauseLink"]
    pending_encounter_id: str | None = None  # EncounterPending 时等待的库内事件
    pending_scenario: PendingScenario | None = None
    scene_focus: str | None = None  # 如"金龙鱼"，供「去围观」解析

    # —— 先天属性（GAME_DESIGN §6.1 / §7.5，ARCHITECTURE 未建模，此处按内容设计补齐）——
    spirit_root: str = ""  # 灵根，如"水木双灵根"
    aptitude: float = 1.0  # 资质：修炼速度倍率，正态分布均值 1.0（"中人之姿"）
    luck: float = 0.0  # 运势：均匀分布，隐藏谓词 luck_gte 读它，不在编辑器谓词白名单里暴露
    insight: float = 0.0  # 悟性：影响顿悟类奇遇的 novelty_curve_override 恢复速度
    origin: str = ""  # 出身：商贾/农家/散修/宗门弟子…决定初始 flags 与可用别名

    # —— 交互流程的挂起态（GAME_DESIGN §1.1 / §4.3，与 pending_encounter 同类，必须进快照）——
    turn_count: int = 0  # 已处理的玩家输入轮数；驱动"提示只出现在前 3 轮"（§1.1）
    pending_retreat_prompt: bool = False  # 已说"闭关"，等待"闭关多久"的回答（§4.3）
    consecutive_breakthrough_failures: int = 0  # 连续突破失败次数，达阈值触发走火入魔（§7.2）

    def as_eval_context(self, world: "WorldView | None" = None) -> EvalContext:
        return _AgentEvalContext(self, world)
