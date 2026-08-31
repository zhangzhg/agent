# EventHorizon 核心底座详细设计文档（Python 实现）

本文档是 [README.md](README.md) 第一部分（底座设计）与第三部分（技术方案）的落地实现设计，只覆盖**核心底座**（事件驱动引擎本身），不含前端/编辑器 UI 的界面实现。目标读者是负责用 Python 实现该引擎的开发者。

**技术前提**：Python 3.11+；全量类型标注；`dataclasses` + `typing.Protocol` + `enum` 构建贫血模型；持久化用标准库 `sqlite3`（不引入 ORM 全量映射，保持结构透明、便于 Event Sourcing 重放）。

**目录分层**：`model`（领域 + 用例 + 数据访问）、`view`（叙述渲染）、`controller`（薄入口）。对局主循环在 `model/services/play_turn.py`，不在 controller 里手写两段流水线。下面先总览，再逐层展开。

---

## 1. 分层架构总览

```
controller/        ← 请求入口：解析输入、调度 model、选 view 渲染输出
     │  依赖
model/              ← 业务全部，内部再分三个子层
  ├─ domain/           纯业务模型：事件、谓词、状态机、时间、因果（零外部依赖，无 IO）
  ├─ services/          用例编排：总线、仲裁、责任链、策略、匹配、工厂、插件
  └─ repositories/       SQLite 持久化、EmbeddingService、LlmEventAuthor 适配器
view/                ← 输出渲染：叙述文本拼装、状态差分格式化、API 响应 DTO
```

**依赖方向**：`controller → model.services → model.domain`。`repositories` 实现 `services.ports` 里的 `Protocol`，反向注入。`view` 只认 `TurnResult` 等用例产出，不依赖 `PipelineContext`，不持有 repository。

**对局唯一入口**：玩家聊天、NPC 日程、时钟到点，都 `EventBus.publish` 一条已解析好的 `GameEventOccurrence`（或先 publish 命令意图，由 `PlayTurnService` 订阅后补全）。`PlayTurnService` 内顺序：仲裁 → 谓词校验 → 状态机 → 责任链**产出 diff** → 一次性 apply → 记日志 → 再决定是否抽第二段。状态类**不持有** `EventBus`，只返回下一状态；由 `PlayTurnService` 在成功后 `publish(AgentStateChanged)`。

**结算事务（硬约束）**：结果池**只计算 diff，不直接改 `Agent` / `World`**。责任链跑完得到 `AppliedDiff` + `WorldDiff`，由 `ApplyDiffStep` 一次性打进内存状态，再落日志。好处有三：中途抛异常时状态未被半改；日志里的 diff 与实际发生的完全一致；**读档重放与实时对局共用同一段 apply 代码**，不存在"两套结算"。

**时间模型（MVP 决策）**：MVP **回合驱动**——游戏时间只由事件的 `duration_shichen` 推进，不开墙钟线程，`TimeDilation` 字段保留但恒为 1，界面时间即游戏时间。README 1.2.1 描述的"日历服务内部墙钟循环"推迟到 V1；闭关是**同步的批量结算循环**（见 §4.11），不是后台线程。这样 §10 的"单线程、总线队列不上锁"才成立。

**挂起态（跨回合交互）**：奇遇的"下一句选分支"与流程图内部分支，统一由 `Agent` 上的挂起字段承载（`pending_encounter_id` / `pending_scenario`），**必须进快照**。服务对象一律无跨回合状态。

**禁止**：在 `controller` 里直调 `pipeline.run` / `coarse_filter`；在状态类里改背包；结果池执行器直接写 `Agent` 字段；服务对象持有跨回合状态；对局路径注入 `LlmAuthorPort`。

---

## 2. 项目目录结构

```
eventhorizon/
├── model/
│   ├── domain/                    # 纯业务实体与规则（§3）
│   │   ├── time.py                   # GameTime, GameCalendar, TimeDilation, AgentTimeAnchor
│   │   ├── map.py                     # Location, Route
│   │   ├── predicates.py               # Predicate / PredicateGroup（谓词白名单，替代 eval）
│   │   ├── events.py                    # GameEventDef, GameEventOccurrence, EventVariant, ReplyOption
│   │   ├── results.py                    # 类型化结果池（禁止 payload: dict）
│   │   ├── diff.py                        # AppliedDiff / WorldDiff / apply / invert（唯一改状态处）
│   │   ├── balance.py                      # BalanceTable：突破、战斗、修炼系数
│   │   ├── items.py                         # ItemDef, Inventory
│   │   ├── scenario.py                       # ScenarioGraph, ScenarioNode, ScenarioEdge
│   │   ├── cause.py                           # CauseLink
│   │   ├── agent.py                            # Agent, AgentEventHistory, Biography
│   │   └── states.py                            # AgentState 状态机（状态模式）
│   ├── services/                  # 用例编排（§4）
│   │   ├── ports.py                  # EventRepository / SnapshotStore / EmbeddingPort / LlmAuthorPort
│   │   ├── play_turn.py               # 对局两段循环（唯一编排处）
│   │   ├── turn_result.py              # TurnResult：给 view 的用例产出
│   │   ├── event_bus.py                 # EventBus（延后投递）
│   │   ├── arbiter.py                    # EventArbiter
│   │   ├── pipeline.py                    # 责任链：产 diff → apply → log
│   │   ├── registry.py                     # EventRegistry：总线 type + event_id 两套键
│   │   ├── plugin_loader.py                 # MVP 只用 load_static
│   │   ├── handlers/
│   │   │   ├── game_event_handler.py           # 库内一般事件共用策略
│   │   │   ├── result_pool_executor.py          # Result 联合类型的唯一分发点
│   │   │   ├── time_pass_handler.py
│   │   │   ├── map_update_handler.py
│   │   │   └── death_handler.py
│   │   ├── matching.py                            # 粗筛（含冷却/次数/互斥）+ 新鲜度 + 变体选择
│   │   ├── chat_parser.py                          # 文本 → event_id / 挂起态选项
│   │   ├── scenario_executor.py                     # 无状态：进度存 Agent.pending_scenario
│   │   ├── event_validation.py                       # 编辑器与 LlmEventAuthor 共用的校验（§4.12）
│   │   ├── schedule_service.py                        # 日程：提高标签权重（§4.13）
│   │   ├── death_service.py                            # 死亡结算与转世/夺舍/继承（§4.13）
│   │   └── clock_service.py                             # 回合驱动时间推进 + 闭关批量结算（§4.11）
│   └── repositories/              # 数据访问与外部适配（§5）
│       ├── sqlite_event_repository.py
│       ├── event_log.py               # Event Sourcing 增量日志
│       ├── snapshot_store.py
│       ├── embedding/
│       │   ├── null_embedding.py         # MVP：向量模块关闭时的空实现
│       │   └── sqlite_vector_index.py     # V2
│       └── llm/
│           └── llm_event_author.py          # 仅录入侧，对局侧不可达（1.3.4）
├── view/                           # 输出渲染（§6，新增）
│   ├── narrative_renderer.py          # 叙述文本拼装：选中的 EventVariant + 占位符上下文 → 最终文案
│   ├── state_diff_view.py              # 结构化状态差分的对外展现格式
│   ├── calendar_view.py                 # 万年历界面展示数据组装（1.2.1 罗盘/干支历牌）
│   └── schemas/                          # API 请求/响应 DTO
│       ├── chat_schemas.py
│       └── editor_schemas.py
├── controller/                     # 请求入口（§7，原 interface 层）
│   ├── chat_controller.py             # 薄：parse 失败回文，否则 play_turn.handle_player_text
│   ├── editor_controller.py
│   └── cli_controller.py                # MVP 入口；ws_controller 放到 V1
└── tests/
    ├── model/
    │   ├── domain/
    │   ├── services/
    │   └── repositories/
    ├── view/
    └── controller/
```

每个子包边界与 README 术语表一一对应，新增字段/术语先落在 `model/domain`，再由 `model/services` 编排，最后由 `view` 决定怎么呈现、`controller` 决定怎么接request。

---

## 3. model/domain 层设计

### 3.1 时间（对应 1.2.1 / 1.6）

```python
# model/domain/time.py
from dataclasses import dataclass
from enum import Enum

class Epoch(str, Enum):
    TAIYI = "太乙历"

@dataclass(frozen=True, slots=True)
class GameTime:
    """纪元 -> 年(干支) -> 月 -> 日 -> 时辰，可比较、可加减"""
    epoch: Epoch
    year: int
    ganzhi: str
    month: int
    day: int
    shichen: int  # 0-11

    def __lt__(self, other: "GameTime") -> bool: ...
    def add_shichen(self, n: int) -> "GameTime": ...

@dataclass(slots=True)
class TimeDilation:
    """游戏时间 : 现实时间，如 60 表示 1 现实秒 = 60 游戏秒"""
    ratio: float

@dataclass(slots=True)
class AgentTimeAnchor:
    """1.6 个体时间锚：Agent 当前游戏时间 = last_synced + pending_duration"""
    last_synced_game_time: GameTime
    pending_duration_shichen: int = 0

    @property
    def current_game_time(self) -> GameTime:
        return self.last_synced_game_time.add_shichen(self.pending_duration_shichen)
```

`GameCalendar` 是无状态的纯函数集合（干支推算、灵气潮汐日判定），不持有可变状态；可变的"当前时刻"只存在于 `model/services/clock_service.py` 里的单例。

### 3.2 谓词（对应 1.3.1，白名单替代 eval）

```python
# model/domain/predicates.py
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

class PredicateType(str, Enum):
    ATTR_GTE = "attr_gte"
    ATTR_EQ = "attr_eq"
    REALM_GTE = "realm_gte"  # 境界有序比较，不用 float
    MONEY_GTE = "money_gte"
    AGE_GTE = "age_gte"
    HAS_ITEM = "has_item"
    FLAG = "flag"
    LOCATION_TYPE = "location_type"
    HAS_CAUSE = "has_cause"

@dataclass(frozen=True, slots=True)
class Predicate:
    type: PredicateType
    args: tuple[Any, ...]

class EvalContext(Protocol):
    """粗筛/门控/流程图/录入沙盒共用。境界用 realm_gte，不用 attr 冒充。"""
    def attr(self, name: str) -> float: ...
    def realm_rank(self) -> int: ...
    def money(self) -> int: ...
    def age(self) -> int: ...
    def has_item(self, item_id: str) -> bool: ...
    def flag(self, name: str) -> bool: ...
    def location_type(self) -> str: ...
    def has_cause(self, tag: str, target: str) -> bool: ...

# REALM_ORDER 在 domain 常量里：凡人=0 … 仙人=N
_EVALUATORS = {
    PredicateType.ATTR_GTE: lambda ctx, a: ctx.attr(a[0]) >= a[1],
    PredicateType.ATTR_EQ: lambda ctx, a: ctx.attr(a[0]) == a[1],
    PredicateType.REALM_GTE: lambda ctx, a: ctx.realm_rank() >= a[0],
    PredicateType.MONEY_GTE: lambda ctx, a: ctx.money() >= a[0],
    PredicateType.AGE_GTE: lambda ctx, a: ctx.age() >= a[0],
    PredicateType.HAS_ITEM: lambda ctx, a: ctx.has_item(a[0]),
    PredicateType.FLAG: lambda ctx, a: ctx.flag(a[0]),
    PredicateType.LOCATION_TYPE: lambda ctx, a: ctx.location_type() == a[0],
    PredicateType.HAS_CAUSE: lambda ctx, a: ctx.has_cause(a[0], a[1]),
}

def evaluate(p: Predicate, ctx: EvalContext) -> bool:
    return _EVALUATORS[p.type](ctx, p.args)

@dataclass(frozen=True, slots=True)
class PredicateGroup:
    """AND/OR 组合，禁止任意字符串 eval；录入编辑器的谓词构建器产出同一结构"""
    op: str  # "AND" | "OR"
    items: tuple["Predicate | PredicateGroup", ...]

    def evaluate(self, ctx: EvalContext) -> bool:
        results = (
            evaluate(i, ctx) if isinstance(i, Predicate) else i.evaluate(ctx)
            for i in self.items
        )
        return all(results) if self.op == "AND" else any(results)
```

这份 `PredicateGroup` 同时服务三处：`model/services/matching.py` 粗筛、`model/services/scenario_executor.py` 流程图边跳转、`controller/editor_controller.py` 的"模拟触发"沙盒——三处复用同一套定义，避免"编辑器和运行时两套标准"（对应 README 1.3.3 的联动校验约束）。

### 3.3 事件（对应 1.3.2 / 1.4.3）

```python
# model/domain/events.py
from dataclasses import dataclass
from enum import Enum
from model.domain.predicates import PredicateGroup

class TriggerSource(str, Enum):
    PLAYER = "player"
    SCHEDULE = "schedule"
    ENCOUNTER = "encounter"
    FORCE = "force"
    CHAIN = "chain"

@dataclass(frozen=True, slots=True)
class EventVariant:
    text: str
    weight: float = 1.0

@dataclass(frozen=True, slots=True)
class ReplyOption:
    """跨回合分支：奇遇挂起后，玩家下一句在这张局部表里解析（「买下来」「算了」）。
    非空即表示本条事件 needs_reply——取代原先用 tags 里塞魔法字符串的做法。"""
    aliases: tuple[str, ...]
    results: tuple["Result", ...] = ()
    chain_event_id: str | None = None

# 结果池见 model/domain/results.py，不用 payload: dict

@dataclass(frozen=True, slots=True)
class GameEventDef:
    """事件库中的一条定义（录入产物），不可变；运行时不修改它"""
    event_id: str
    applicable_locations: tuple[str, ...]
    applicable_time: tuple[int, ...] | None
    predicate: PredicateGroup | None
    weight: float
    duration_shichen: int          # README 核心诉求 2「持续时间」：时间推进的唯一来源
    cooldown_shichen: int
    max_trigger_per_agent: int | None
    exclusive_tags: tuple[str, ...]
    priority: int                   # 仲裁默认等级，被 TriggerSource 覆盖（README 1.7）
    tags: tuple[str, ...]
    aliases: tuple[str, ...]
    result_pool: tuple["Result", ...]
    variants: tuple[EventVariant, ...]
    reply_options: tuple[ReplyOption, ...] = ()
    novelty_curve_override: dict | None = None
    scenario_ref: str | None = None
    schema_version: int = 1
    is_draft: bool = False
    is_command: bool = False  # True=命令型（eat/move），False=第二段奇遇

    @property
    def needs_reply(self) -> bool:
        return bool(self.reply_options) or self.scenario_ref is not None

@dataclass(slots=True)
class GameEventOccurrence:
    event_id: str
    trigger_source: TriggerSource
    agent_id: str
    occurred_at: "GameTime"
    chosen_variant_index: int
    applied_diff: "AppliedDiff | None" = None
    world_diff: "WorldDiff | None" = None
    def_schema_version: int = 1
```

`GameEventDef` 与 `Occurrence` 分离。日志必须带 `applied_diff`（世界级变更另带 `world_diff`）：录入日后改结果池，旧档仍按当时差分重放。读档 = 快照 + 逐条 apply diff，**禁止**对历史再跑 matching / 责任链。

### 3.3.1 差分（`diff.py`，唯一改状态处）

```python
# model/domain/diff.py
from dataclasses import dataclass, replace

@dataclass(frozen=True, slots=True)
class AppliedDiff:
    """Agent 级差分。数值一律走 attr_deltas，不写死字段清单——
    修为/心魔/寿元/悟性等 README 2.4 的后天属性都从这里过，避免加一个属性就改一次结构。"""
    attr_deltas: tuple[tuple[str, float], ...] = ()   # ("satiety", +3) ("money", -5) ("cultivation", +12) ("lifespan", -1)
    realm_set: str | None = None                       # 境界是有序枚举，不当 float 加减
    location_set: str | None = None
    items_add: tuple[tuple[str, int], ...] = ()
    items_remove: tuple[tuple[str, int], ...] = ()
    flags_set: tuple[str, ...] = ()
    flags_clear: tuple[str, ...] = ()
    causes_add: tuple["CauseLink", ...] = ()
    time_shichen_delta: int = 0
    scene_focus_set: str | None = None
    pending_encounter_set: str | None = None
    pending_scenario_set: "PendingScenario | None" = None
    state_set: str | None = None                       # 状态机结果也进 diff，重放才能还原挂起态

@dataclass(frozen=True, slots=True)
class LocationAttrChange:
    location_id: str
    key: str          # 灵气浓度 / 危险等级 / 状态（完好|废墟|秘境开启）
    old: float | str  # 记 old 才能反向回滚（README 1.8 焦土复原）
    new: float | str

@dataclass(frozen=True, slots=True)
class WorldDiff:
    """世界级差分。地图改动落在快照之后时，只有它能让重放不丢。"""
    location_changes: tuple[LocationAttrChange, ...] = ()

    def invert(self) -> "WorldDiff":
        return WorldDiff(tuple(
            LocationAttrChange(c.location_id, c.key, c.new, c.old) for c in self.location_changes
        ))

def merge(a: AppliedDiff, b: AppliedDiff) -> AppliedDiff: ...
def apply_agent_diff(agent: "Agent", d: AppliedDiff) -> None: ...
def apply_world_diff(world: "WorldState", d: WorldDiff) -> None: ...
```

**这三个 `apply_*` 是全系统唯一改 `Agent` / `World` 的地方。** 实时对局与读档重放调用的是同一个函数——不存在"实时一套、回放一套"。地图回滚（README 1.8）= 取该 `Occurrence` 的 `world_diff.invert()` 再 apply。

### 3.3.2 类型化结果（`results.py`）

```python
# model/domain/results.py
from dataclasses import dataclass
from typing import Union

@dataclass(frozen=True, slots=True)
class ItemDrop:
    item_id: str
    n: int = 1

@dataclass(frozen=True, slots=True)
class ItemConsume:
    item_id: str
    n: int = 1

@dataclass(frozen=True, slots=True)
class StateChange:
    field: str  # satiety | money | cultivation | heart_demon | location
    delta: int | None = None
    set_to: str | int | None = None

@dataclass(frozen=True, slots=True)
class Check:
    kind: str  # breakthrough | combat
    # 系数不写在这里：执行时按 kind 从 BalanceTable 读公式参数（§3.5）
    # 成功/失败各挂一条后续 Result 或 chain event_id
    on_success: tuple["Result", ...] = ()
    on_fail: tuple["Result", ...] = ()

@dataclass(frozen=True, slots=True)
class WriteCause:
    tag: str
    target: str
    expires_years: int | None = None

@dataclass(frozen=True, slots=True)
class ChainEvent:
    event_id: str
    source_override: "TriggerSource" = TriggerSource.CHAIN

@dataclass(frozen=True, slots=True)
class StartScenario:
    scenario_id: str

Result = Union[ItemDrop, ItemConsume, StateChange, Check, WriteCause, ChainEvent, StartScenario]
```

扣饭钱、加饱食、移动地点**只**走 `StateChange` / `ItemConsume`，责任链不再另设「扣资源」步。执行器把每条 `Result` **翻译成 `AppliedDiff` 片段并累加**，自己不碰 `Agent`。

### 3.3.3 Agent 与物品

```python
# model/domain/items.py
@dataclass(frozen=True, slots=True)
class ItemDef:
    item_id: str
    kind: str  # food | pill | manual | material | gear
    stackable: bool
    unique: bool

# model/domain/agent.py
@dataclass(slots=True)
class Inventory:
    counts: dict[str, int]

    def has(self, item_id: str) -> bool: ...
    def add(self, item_id: str, n: int = 1) -> None: ...
    def consume(self, item_id: str, n: int = 1) -> bool: ...

@dataclass(frozen=True, slots=True)
class PendingScenario:
    """流程图跨回合进度。存在 Agent 上而非 ScenarioExecutor 里，才能进快照。"""
    scenario_id: str
    current_node_id: str
    host_event_id: str

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
    lifespan_left: float          # 寿元，闭关按结算跨度扣（README 2.4）
    flags: set[str]
    inventory: Inventory
    time_anchor: AgentTimeAnchor
    event_history: "AgentEventHistory"
    state: "AgentState"
    causes: list["CauseLink"]
    pending_encounter_id: str | None = None   # EncounterPending 时等待的库内事件
    pending_scenario: PendingScenario | None = None
    scene_focus: str | None = None            # 如 金龙鱼，供「去围观」解析

    def as_eval_context(self, world: "WorldView") -> EvalContext: ...
```

`WorldView` 只读地点属性、天气、全局时钟，由 services 组装，domain 不碰 IO。

### 3.3.4 `AgentEventHistory`（粗筛与新鲜度的唯一数据源）

全文档多处引用，此处给定契约。它随 Agent 存档，不是缓存。

```python
# model/domain/agent.py
@dataclass(slots=True)
class AgentEventHistory:
    triggers: dict[str, list["GameTime"]]        # event_id → 触发时刻（按窗口截断，不无限增长）
    variant_cursor: dict[str, int]                # event_id → 上次用过的变体下标
    recent_tags: list[tuple[str, "GameTime"]]      # 标签滚动窗口，供配额补偿

    # —— 粗筛用（硬过滤，README 1.4.2）——
    def in_cooldown(self, event_id: str, now: "GameTime", cooldown_shichen: int) -> bool: ...
    def trigger_count(self, event_id: str) -> int: ...
    def active_exclusive_tags(self, now: "GameTime") -> set[str]: ...

    # —— 重排用（软乘子，README 1.4.3）——
    def recency_factor(self, event_id: str, curve: dict | None) -> float: ...
    def tag_quota_factor(self, tags: tuple[str, ...]) -> float: ...

    # —— 变体轮换（README 1.4.3 文案变体）——
    def last_variant(self, event_id: str) -> int | None: ...

    def record(self, event_id: str, at: "GameTime", tags: tuple[str, ...], variant: int) -> None: ...
```

**冷却/次数/互斥是硬过滤，进 `coarse_filter`；recency/配额/长尾是软乘子，进 `reweight_and_pick`。** 两者不可混用：冷却期内的事件必须彻底不出现，而不是权重降低。

### 3.4 `BalanceTable`（数值集中配置）

```python
# model/domain/balance.py
@dataclass(frozen=True, slots=True)
class BalanceTable:
    """README 2.4 的数值骨架，集中配置便于调优。Check 执行器按 kind 读这里，
    公式里不出现具体物品名或事件 id。"""
    realm_order: tuple[str, ...]                  # 凡人 → 练气 → … → 仙人，REALM_GTE 比较的依据
    breakthrough: dict[str, float]                 # 资质/灵气/丹药系数、心魔惩罚、境界惩罚、clamp 上下界
    combat: dict[str, float]                        # 境界差、道具、运势、心魔权重，clamp(0.05, 0.95)
    cultivation_rate: dict[str, float]               # 打坐每时辰修为 = f(资质, 灵气浓度)
    lifespan_by_realm: dict[str, float]               # 各境界寿元上限

    def realm_rank(self, realm: str) -> int:
        return self.realm_order.index(realm)
```

以 JSON/TOML 随存档版本一起分发；`Check` 与 `EvalContext.realm_rank()` 都读它，避免境界顺序在两处各写一份。

### 3.5 Agent 状态机（对应 3.3，状态模式）

```python
# model/domain/states.py
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from model.domain.agent import Agent
    from model.domain.events import GameEventOccurrence

class AgentState(ABC):
    name: str

    @abstractmethod
    def try_transition(self, agent: "Agent", incoming: "GameEventOccurrence") -> "AgentState | None":
        """返回新状态则转换成功；返回 None 则拒绝（非法指令在此拦，不散落在 Handler 里）"""

    def settle(self, agent: "Agent") -> "AgentState":
        """结算收尾的落点：本轮跑完后由 PlayTurn 调用，决定回 Idle 还是进挂起态。
        禁止在 PlayTurn 里直接 `agent.state = IdleState()` —— 那样绕开了状态机，
        README 3.3「状态切换必须经状态对象」就成了空话。"""
        if agent.pending_scenario is not None:
            return ScenarioPendingState()
        if agent.pending_encounter_id is not None:
            return EncounterPendingState()
        return IdleState()

class IdleState(AgentState):
    name = "idle"
    def try_transition(self, agent, incoming):
        from model.domain.events import TriggerSource
        if incoming.trigger_source in (
            TriggerSource.PLAYER, TriggerSource.SCHEDULE, TriggerSource.FORCE, TriggerSource.ENCOUNTER
        ):
            return ActingState()
        return None

class ActingState(AgentState):
    name = "acting"
    def try_transition(self, agent, incoming):
        from model.domain.events import TriggerSource
        if incoming.trigger_source == TriggerSource.FORCE:
            return ActingState()  # 打断后仍在行动中结算强制事件
        if incoming.trigger_source == TriggerSource.PLAYER:
            return ActingState()  # 抢占：新命令替换当前主行为（旧行为由 PlayTurn 丢弃/入队）
        return None  # ENCOUNTER 在 acting 时不转换，由 PlayTurn 决定挂起或同回合叙述

class ClosedDoorState(AgentState):
    name = "closed_door"
    def try_transition(self, agent, incoming):
        from model.domain.events import TriggerSource
        if incoming.trigger_source == TriggerSource.FORCE:
            return ActingState()
        return None

class EncounterPendingState(AgentState):
    name = "encounter_pending"
    def try_transition(self, agent, incoming):
        from model.domain.events import TriggerSource
        if incoming.trigger_source in (TriggerSource.PLAYER, TriggerSource.FORCE):
            return ActingState()
        return None

class ScenarioPendingState(AgentState):
    """流程图执行中，等玩家下一句选边。与 EncounterPending 的区别：
    挂起的是 pending_scenario（图内节点），不是一条待接受的奇遇。"""
    name = "scenario_pending"
    def try_transition(self, agent, incoming):
        from model.domain.events import TriggerSource
        if incoming.trigger_source in (TriggerSource.PLAYER, TriggerSource.FORCE):
            return ActingState()
        return None

class DeadState(AgentState):
    name = "dead"
    def try_transition(self, agent, incoming):
        return None

    def settle(self, agent):
        return self  # 死亡是吸收态，只由 death_service 的重玩流程换人
```

**顺序（硬约束）**：仲裁通过 → `predicate.evaluate` → `try_transition` → 跑结果池**产 diff** → apply → `settle()` 定落点。谓词失败则状态不变、不产 diff、不写日志。

状态类不持有 `EventBus`。`PlayTurnService` 在转换成功后 `publish(AgentStateChanged)`。结算收尾一律走 `state.settle(agent)`，落点由挂起字段决定：有 `pending_scenario` → `ScenarioPending`；有 `pending_encounter_id` → `EncounterPending`；都没有 → `Idle`。同回合纯叙述的奇遇（金龙鱼出现）不写挂起字段，`settle` 自然回 `Idle`；需要玩家下一句的事件靠 `GameEventDef.needs_reply`（由 `reply_options` / `scenario_ref` 推导）区分，**不再用 tags 里的魔法字符串**。

---

## 4. model/services 层设计（事件流水线）

对应 README 3.0 的默认路径：

```
生产者 publish → EventBus → EventArbiter → 责任链 → EventHandler 策略 → 状态机 → 可能再 publish
```

### 4.1 EventBus（观察者模式）

```python
# model/services/event_bus.py
from collections import defaultdict
from typing import Callable, Protocol, TypeVar

E = TypeVar("E")

class EventBus(Protocol):
    def publish(self, event: object) -> None: ...
    def subscribe(self, event_type: type[E], handler: Callable[[E], None]) -> None: ...

class InProcessEventBus:
    """同步订阅，但 publish 入队；本轮 dispatch 出栈后再投递下游，避免突破→走火入魔重入。"""
    def __init__(self) -> None:
        self._subs: dict[type, list[Callable]] = defaultdict(list)
        self._queue: list[object] = []
        self._flushing: bool = False

    def subscribe(self, event_type: type[E], handler: Callable[[E], None]) -> None:
        self._subs[event_type].append(handler)

    def publish(self, event: object) -> None:
        self._queue.append(event)
        if not self._flushing:
            self._flush()

    def _flush(self) -> None:
        self._flushing = True
        try:
            while self._queue:
                event = self._queue.pop(0)
                for handler in self._subs[type(event)]:
                    handler(event)
        finally:
            self._flushing = False
```

`PlayTurnService` 订阅 `GameEventOccurrence`。Clock / 日程 / matching **只** `publish` Occurrence，不直调 pipeline。`ChatParser` 不是生产者：它只把文本变成 `event_id`，由 `PlayTurnService.handle_player_text` 组 Occurrence 再 publish（或直接走内部 `execute_occurrence`，与订阅者同一函数，避免两套逻辑）。

### 4.2 EventArbiter（对应 1.7）

```python
# model/services/arbiter.py
from enum import Enum, auto
from model.domain.events import TriggerSource

class ArbitrationDecision(Enum):
    EXECUTE = auto()
    ENQUEUE = auto()
    DISCARD = auto()

SOURCE_RANK = {  # 数字小 = 强，对应 README 1.7 的四级
    TriggerSource.FORCE: 0,
    TriggerSource.PLAYER: 1,
    TriggerSource.SCHEDULE: 2,
    TriggerSource.ENCOUNTER: 3,
    TriggerSource.CHAIN: 1,  # 默认随触发它的那条，由调用方显式覆盖
}

class EventArbiter:
    def decide(
        self,
        agent_current_state: str,
        incoming_source: TriggerSource,
        incoming_priority: int,        # GameEventDef.priority，录入时配置的默认等级
        current_priority: int | None,   # 正在进行的主行为等级；idle 时为 None
    ) -> ArbitrationDecision:
        """README 1.7：读事件元数据的默认优先级，投递时的 TriggerSource 可覆盖。
        实际等级 = (SOURCE_RANK[source], incoming_priority)，先比来源再比事件配置。"""
        if incoming_source is TriggerSource.FORCE:
            return ArbitrationDecision.EXECUTE          # 强制级立即中断
        if agent_current_state == "dead":
            return ArbitrationDecision.DISCARD
        if agent_current_state == "closed_door":
            return ArbitrationDecision.DISCARD          # 非 force 一律不打扰闭关
        if agent_current_state in ("encounter_pending", "scenario_pending"):
            # 挂起等回话期间，只认玩家；日程/奇遇丢弃，避免把玩家的选择窗口冲掉
            return (ArbitrationDecision.EXECUTE if incoming_source is TriggerSource.PLAYER
                    else ArbitrationDecision.DISCARD)
        if agent_current_state == "acting":
            if incoming_source is TriggerSource.PLAYER:
                return ArbitrationDecision.EXECUTE      # 玩家抢占日程
            if incoming_source is TriggerSource.ENCOUNTER:
                return ArbitrationDecision.ENQUEUE      # 奇遇不抢主行为，挂为可选分支
            if current_priority is not None and incoming_priority < current_priority:
                return ArbitrationDecision.EXECUTE      # 同来源下按事件配置的等级比
            return ArbitrationDecision.DISCARD
        return ArbitrationDecision.EXECUTE
```

**`ENQUEUE` 的语义是明确的**：不执行结果池，只把 `event_id` 写进 `agent.pending_encounter_id`（经 diff），等主行为结束后由玩家下一句决定接不接（README 1.7「奇遇作为可选分支挂在当前行为上」）。`PlayTurnService` 必须显式处理这个分支——**把 ENQUEUE 当 EXECUTE 放过去，就等于奇遇抢占了主行为**。同一时刻只允许一个挂起项：已有 `pending_encounter_id` 时新的 ENQUEUE 直接丢弃，不排队堆积。

### 4.3 责任链（对应 3.6）

```python
# model/services/pipeline.py
from dataclasses import dataclass
from typing import Protocol

@dataclass
class PipelineContext:
    occurrence: "GameEventOccurrence"
    event_def: "GameEventDef"
    agent: "Agent"          # 只读快照来源；步骤禁止直接赋值它的字段
    world: "WorldView"
    rejected: bool = False   # 校验未过：什么都没发生，不 apply、不写日志
    stopped: bool = False     # 中途终止：已产出的 diff 仍然生效
    diff: "AppliedDiff" = field(default_factory=AppliedDiff)     # 累加中的 Agent 差分
    world_diff: "WorldDiff" = field(default_factory=WorldDiff)
    chosen_variant: int = 0
    spawned: list["GameEventOccurrence"] = field(default_factory=list)  # 待 publish 的连锁

class PipelineStep(Protocol):
    def handle(self, ctx: PipelineContext) -> None: ...

class ValidationStep:
    def handle(self, ctx: PipelineContext) -> None:
        if ctx.event_def.predicate and not ctx.event_def.predicate.evaluate(ctx.agent.as_eval_context(ctx.world)):
            ctx.rejected = True

# 不设 ResourceStep：扣钱/食物/时间只在结果池 StateChange / ItemConsume

class DomainStrategyStep:
    """策略只往 ctx.diff 累加，不碰 ctx.agent 的字段。"""
    def __init__(self, handler: "EventHandler") -> None:
        self._handler = handler
    def handle(self, ctx: PipelineContext) -> None:
        self._handler.handle(ctx)

class ApplyDiffStep:
    """全链唯一的写入点。跑到这里说明结果池已全部算完、没有抛异常。"""
    def handle(self, ctx: PipelineContext) -> None:
        if ctx.rejected:
            return
        apply_agent_diff(ctx.agent, ctx.diff)
        apply_world_diff(ctx.world.mutable_state(), ctx.world_diff)

class LogStep:
    """把 diff 挂到 Occurrence 上并追加日志（脏标记，不做全量快照）。
    CauseLink 已经在 ctx.diff.causes_add 里，这里不再单独写一遍。"""
    def handle(self, ctx: PipelineContext) -> None: ...

class Pipeline:
    """固定顺序，插件不能插队到校验之前（3.5 约束）：
    Validation → DomainStrategy → ApplyDiff → Log"""
    def __init__(self, steps: list[PipelineStep]) -> None:
        self._steps = steps

    def run(self, ctx: PipelineContext) -> PipelineContext:
        for step in self._steps:
            if ctx.rejected:
                break                      # 校验未过：连 ApplyDiff 都不跑
            if ctx.stopped and not isinstance(step, (ApplyDiffStep, LogStep)):
                continue                    # 中途终止仍要落已产出的 diff
            step.handle(ctx)
        return ctx
```

`rejected` 与 `stopped` 必须分开：前者是"这条事件根本不该发生"（状态原样、无日志），后者是"算到一半不再往下算，但已发生的照落"。混成一个布尔量会让突破失败这类事件要么丢掉扣除、要么把谓词失败也记进日志。

复杂事件（突破失败 → 走火入魔）在 `DomainStrategyStep` 内部 `ctx.stopped = True` 并把新 Occurrence 塞进 `ctx.spawned`，由 `PlayTurnService` 在本轮 apply 落地后统一 `publish`——不在链上无限分叉，也不会在状态尚未写入时就触发下游（对应 3.6 最后一条约束）。

### 4.4 EventHandler 策略（对应 3.2）

```python
# model/services/handlers/game_event_handler.py
from typing import Protocol
from model.services.pipeline import PipelineContext

class EventHandler(Protocol):
    def handle(self, ctx: PipelineContext) -> None: ...

class GameEventHandler:
    """事件库一般事件共用一个策略：eat/meditate/breakthrough/奇遇同一个类，
    差异只来自 ctx.event_def.result_pool，不写 switch"""
    def __init__(self, result_pool_executor: "ResultPoolExecutor") -> None:
        self._executor = result_pool_executor

    def handle(self, ctx: PipelineContext) -> None:
        for entry in ctx.event_def.result_pool:
            self._executor.execute(entry, ctx)
```

`ResultPoolExecutor` 对 `Result` 联合类型做 `match`，把每条结果**翻译成 diff 片段累加进 `ctx.diff` / `ctx.world_diff`**，自己不改 `Agent`。这是唯一允许的结果分发点。`Check` 从 `BalanceTable` 读系数、用注入的 `rng` 掷点，再展开对应分支的 `Result`。`ChainEvent` 只往 `ctx.spawned` 追加 Occurrence，不在本链继续展开。

### 4.5 EventRegistry（对应 3.4，工厂模式）

```python
# model/services/registry.py
from dataclasses import dataclass
from typing import Callable

@dataclass
class RegistryEntry:
    factory: Callable[[dict], object]
    handler: "EventHandler"
    priority: int
    schema_version: int

class EventRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, RegistryEntry] = {}

    def register(self, type_key: str, entry: RegistryEntry) -> None:
        self._entries[type_key] = entry

    def create(self, record: dict) -> object | None:
        """两套键：总线系统事件用 type=TimePassEvent|MapUpdateEvent|DeathEvent|GameEventOccurrence；
        库内玩法用 event_id 从 EventRepository 取 GameEventDef，不要为 eat/meditate 各注册一个 type。"""
        entry = self._entries.get(record.get("type"))
        if entry is None:
            return None
        return entry.factory(_migrate(record, entry.schema_version))

def _migrate(record: dict, target_version: int) -> dict:
    """旧存档字段缺失时在这里填默认值，不在业务 Handler 里做兼容分支"""
    ...
```

### 4.6 PluginLoader（对应 3.5，插件模式）

```python
# model/services/plugin_loader.py
import importlib
from model.services.registry import EventRegistry

class PluginLoader:
    def __init__(self, registry: EventRegistry) -> None:
        self._registry = registry

    def load_static(self, register_fns: list[callable]) -> None:
        """MVP：编译期静态注册，代码里显式列出，不做运行时热加载"""
        for fn in register_fns:
            fn(self._registry)

    def load_manifest(self, manifest: list[dict]) -> None:
        """V1+：{module, register_fn} 清单，用 importlib 动态加载"""
        for item in manifest:
            try:
                module = importlib.import_module(item["module"])
                getattr(module, item["register_fn"])(self._registry)
            except Exception as exc:
                # 失败隔离：单个插件加载失败不影响已注册核心事件
                _log_plugin_failure(item["module"], exc)
```

插件只能拿到 `EventRegistry` 引用，拿不到 `EventBus`/`EventArbiter`/`clock_service`——构造函数签名上就不传，杜绝插件旁路核心规则（3.5 约束）。

### 4.7 两阶段匹配 + 新鲜感机制（对应 1.4.2 / 1.4.3）

```python
# model/services/matching.py
import random
from dataclasses import dataclass
from model.domain.events import GameEventDef, TriggerSource

@dataclass
class MatchContext:
    location: str
    location_type: str
    time_shichen: int
    now: "GameTime"
    age: int
    realm: str
    money: int
    causes: list["CauseLink"]

def coarse_filter(
    pool: list[GameEventDef], ctx: MatchContext, eval_ctx, history: "AgentEventHistory"
) -> list[GameEventDef]:
    """README 1.4.2 的粗筛全集：地点 / 时间 / 谓词 / **冷却 / 次数 / 互斥**。
    后三项是硬过滤，不能降级成权重乘子——冷却期内的事件必须彻底不出现。"""
    blocked_tags = history.active_exclusive_tags(ctx.now)
    out = []
    for e in pool:
        if e.is_draft:
            continue
        if not (ctx.location_type in e.applicable_locations or "*" in e.applicable_locations):
            continue
        if e.applicable_time is not None and ctx.time_shichen not in e.applicable_time:
            continue
        if history.in_cooldown(e.event_id, ctx.now, e.cooldown_shichen):
            continue
        if e.max_trigger_per_agent is not None and history.trigger_count(e.event_id) >= e.max_trigger_per_agent:
            continue
        if blocked_tags & set(e.exclusive_tags):
            continue
        if e.predicate is not None and not e.predicate.evaluate(eval_ctx):
            continue
        out.append(e)
    return out

def novelty_weight(event_def: GameEventDef, history: "AgentEventHistory") -> float:
    """1.4.3：短期记忆衰减 × 标签配额 × 长尾保护，三个乘子相乘"""
    recency = history.recency_factor(event_def.event_id, curve=event_def.novelty_curve_override)
    tag_quota = history.tag_quota_factor(event_def.tags)
    rarity_bonus = 1.5 if history.trigger_count(event_def.event_id) == 0 else 1.0
    return recency * tag_quota * rarity_bonus

def reweight_and_pick(
    candidates: list[GameEventDef], history: "AgentEventHistory", rng: random.Random
) -> GameEventDef | None:
    if not candidates:
        return None
    weights = [c.weight * novelty_weight(c, history) for c in candidates]
    return rng.choices(candidates, weights=weights, k=1)[0]

def pick_variant(defn: GameEventDef, history: "AgentEventHistory", rng: random.Random) -> int:
    """README 1.4.3 文案变体：同一 eventId 命中时优先未用过 / 最久未用的一条。
    别再让 Occurrence 的 chosen_variant_index 恒为 0。"""
    if len(defn.variants) <= 1:
        return 0
    last = history.last_variant(defn.event_id)
    pool = [i for i in range(len(defn.variants)) if i != last] or list(range(len(defn.variants)))
    return rng.choices(pool, weights=[defn.variants[i].weight for i in pool], k=1)[0]
```

`reweight_and_pick` 只做规则新颖度；V2 的向量新颖度以同一函数签名的装饰器/包装形式叠加一个相似度乘子，不改这个函数本身（1.4.3 "是同一步的两个乘子，不是两套系统"）。

### 4.8 ChatParser（对应 1.11）

```python
# model/services/chat_parser.py
from dataclasses import dataclass

@dataclass
class ParsedCommand:
    event_id: str
    location_hint: str | None
    target: str | None
    args: dict

@dataclass
class ParsedReply:
    """挂起态下的解析结果：选中了哪个局部选项 / 哪条流程图出边。"""
    option_index: int | None = None      # 对应 GameEventDef.reply_options
    edge_id: str | None = None            # 对应 ScenarioEdge
    dismissed: bool = False                # 「算了」：放弃挂起项

class ChatParser:
    def __init__(self, alias_to_event_id: dict[str, str]) -> None:
        """短语 → event_id，来自已发布命令型 GameEventDef.aliases（如「吃饭」「去吃点东西」→ eat）"""
        self._alias_to_event_id = alias_to_event_id

    def parse(self, raw_text: str, scene_focus: str | None = None) -> ParsedCommand | None:
        """只做映射。失败返回 None（听不懂）。不调用大模型。
        「去围观」在有 scene_focus 时可映射到 watch，target=scene_focus。"""
        ...

    def parse_reply(
        self, raw_text: str, pending: GameEventDef | None, scenario: "ScenarioGraph | None", node_id: str | None
    ) -> ParsedReply | None:
        """挂起态专用：只在**局部选项表**里匹配（reply_options.aliases 或该节点出边的 aliases）。
        与全局别名表分开，「买下来」不必注册成全局命令事件。"""
        ...
```

**解析优先级（补上原设计缺的一环）**：`Agent` 处于挂起态时，`PlayTurnService` **先调 `parse_reply`**；命中则结算挂起项并清空挂起字段。未命中再回落 `parse` 走全局命令——玩家有权无视奇遇直接走人，此时挂起项按"错过"丢弃（写进 diff，别留悬空 id）。两者都不中才回"听不懂"。

`PlayTurnService` 用 `event_id` 调 `EventRepository.get_by_id`；不是命令型或草稿则当解析失败。

### 4.9 PlayTurnService（对局唯一编排）

```python
# model/services/play_turn.py
from model.services.turn_result import TurnResult

class PlayTurnService:
    def __init__(self, bus, arbiter, pipeline, parser, events, scenarios, rng, log, clock):
        ...  # 构造函数里没有 LlmAuthorPort

    # ---------- 入口：一次玩家输入 ----------
    def handle_player_text(self, agent: Agent, world: WorldView, raw: str) -> TurnResult:
        # 1) 挂起态优先：先试局部选项，再回落全局命令（见 §4.8 解析优先级）
        if agent.pending_scenario is not None or agent.pending_encounter_id is not None:
            resolved = self._try_resolve_pending(agent, world, raw)
            if resolved is not None:
                return resolved
            self._abandon_pending(agent)   # 玩家改主意：挂起项按"错过"清掉，经 diff 落库

        # 2) 常规命令
        cmd = self.parser.parse(raw, agent.scene_focus)
        if cmd is None:
            return TurnResult.parse_failed("听不懂，再说一次？")
        defn = self.events.get_by_id(cmd.event_id)
        if defn is None or defn.is_draft or not defn.is_command:
            return TurnResult.parse_failed("听不懂，再说一次？")
        occ = self._new_occurrence(agent, defn, TriggerSource.PLAYER)
        return self.execute_occurrence(agent, world, occ, defn) or TurnResult.rejected("现在做不了这个。")

    # ---------- 单条事件结算：总线订阅、日程、连锁共用 ----------
    def execute_occurrence(self, agent, world, occ, defn) -> TurnResult | None:
        decision = self.arbiter.decide(
            agent.state.name, occ.trigger_source, defn.priority, self._current_priority(agent)
        )
        if decision is ArbitrationDecision.DISCARD:
            return None
        if decision is ArbitrationDecision.ENQUEUE:
            # 奇遇不抢主行为：只挂起，不跑结果池（§4.2）
            if agent.pending_encounter_id is None:
                self._park_encounter(agent, defn)
            return None

        eval_ctx = agent.as_eval_context(world)
        if defn.predicate and not defn.predicate.evaluate(eval_ctx):
            return TurnResult.rejected("条件未满足。")        # 状态未改、无日志
        new_state = agent.state.try_transition(agent, occ)
        if new_state is None:
            return TurnResult.rejected("现在做不了这个。")
        agent.state = new_state

        ctx = self.pipeline.run(PipelineContext(occ, defn, agent, world))
        if ctx.rejected:
            return TurnResult.rejected("条件未满足。")
        # 时间推进：唯一来源是事件时长（§4.11 回合驱动）
        self.clock.advance_for(agent, defn.duration_shichen)
        agent.event_history.record(defn.event_id, occ.occurred_at, defn.tags, occ.chosen_variant_index)
        agent.state = agent.state.settle(agent)              # 不直接赋 IdleState()
        self.bus.publish(AgentStateChanged(agent.agent_id, agent.state.name))
        for spawned in ctx.spawned:                           # 连锁：apply 落地后再投递
            self.bus.publish(spawned)

        first = TurnResult.from_one(defn, ctx)
        if ctx.stopped:
            return first
        if occ.trigger_source is TriggerSource.PLAYER and defn.is_command:
            return self._second_stage(agent, world, first)
        return first

    # ---------- 第二段：按新状态抽库内事件 ----------
    def _second_stage(self, agent, world, first: TurnResult) -> TurnResult:
        pool = [e for e in self.events.load_event_defs(agent.location_type) if not e.is_command]
        mctx = MatchContext(..., now=self.clock.now())
        candidates = coarse_filter(pool, mctx, agent.as_eval_context(world), agent.event_history)
        picked = reweight_and_pick(candidates, agent.event_history, self.rng)
        if picked is None:
            return first                                      # 抽空：酒楼无事，状态已由上一步 settle
        if picked.needs_reply:
            self._park_encounter(agent, picked)               # 只叙述、不结算，等下一句
            agent.state = agent.state.settle(agent)           # → EncounterPending
            return first.with_prompt(picked, pick_variant(picked, agent.event_history, self.rng))
        occ2 = self._new_occurrence(agent, picked, TriggerSource.ENCOUNTER)
        ctx2 = self.pipeline.run(PipelineContext(occ2, picked, agent, world))
        self.clock.advance_for(agent, picked.duration_shichen)
        agent.event_history.record(picked.event_id, occ2.occurred_at, picked.tags, occ2.chosen_variant_index)
        agent.state = agent.state.settle(agent)
        for spawned in ctx2.spawned:
            self.bus.publish(spawned)
        return first.plus_encounter(picked, ctx2)

    # ---------- 挂起项结算 ----------
    def _try_resolve_pending(self, agent, world, raw) -> TurnResult | None:
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
        # 流程图：推进一个节点，仍未到终点则继续挂起；到终点则清空 pending_scenario
        # 选项表：把 ReplyOption.results 当成一次性结果池跑同一条 pipeline
        ...

    def _new_occurrence(self, agent, defn, source) -> GameEventOccurrence:
        return GameEventOccurrence(
            defn.event_id, source, agent.agent_id, self.clock.now(),
            chosen_variant_index=pick_variant(defn, agent.event_history, self.rng),
        )
```

`# model/services/turn_result.py`：`command_event_id`、`encounter_event_id`、两段 `variant_index`、两段 `AppliedDiff`、`parse_error` / `reject_reason`、`prompt_event_id`（挂起提示）、`scenario_node_id`。view **只**消费 `TurnResult`。

要点：第一段与第二段都 `log.append`（在 `LogStep` 内完成）；变体下标由 `pick_variant` 决定而非恒 0；状态收尾一律 `settle()`；`ENQUEUE` 走挂起而非执行；连锁事件在 apply 之后才 `publish`。

### 4.10 ScenarioExecutor（对应 1.3.1）

```python
# model/services/scenario_executor.py
from model.domain.scenario import ScenarioGraph, ScenarioNode

class ScenarioExecutor:
    """**无状态**。进度存 Agent.pending_scenario，跨回合靠存档带走；
    原先把 _context_stack 挂在实例上的做法，存读档会丢失流程图进度。"""

    def start(self, graph: ScenarioGraph, host_event_id: str) -> tuple[ScenarioNode, PendingScenario]:
        node = graph.entry_node()
        return node, PendingScenario(graph.scenario_id, node.id, host_event_id)

    def advance(
        self, graph: ScenarioGraph, current_node_id: str, eval_ctx, chosen_edge_id: str | None = None
    ) -> ScenarioNode | None:
        """chosen_edge_id 来自 ParsedReply（玩家下一句选的边）；为 None 时按谓词自动走唯一满足的边。"""
        for edge in graph.edges_from(current_node_id):
            if chosen_edge_id is not None and edge.id != chosen_edge_id:
                continue
            if edge.condition.evaluate(eval_ctx):
                return graph.node(edge.to_id)
        return None  # 无边满足则本条事件内流程结束，PlayTurn 清空 pending_scenario
```

节点产出的结果（获得物品、战斗）同样以 `Result` 交给 `ResultPoolExecutor` 走同一条 pipeline，不另开结算路径。流程图节点/边只能引用同一个 `scenario_id` 内的节点——`ScenarioGraph.edges_from` 在构造时校验，杜绝跨事件跳转（对应 1.3.1 "禁止引用主线步骤/章节 id"）。

### 4.11 clock_service：时间推进与闭关（对应 1.6 / 2.3.1）

```python
# model/services/clock_service.py
class GameClock:
    """MVP 回合驱动：游戏时间只因事件时长推进，没有墙钟线程。"""
    def now(self) -> GameTime: ...
    def advance_for(self, agent: Agent, shichen: int) -> None:
        """推进该 Agent 的时间锚；跨过时辰/日边界时 publish TimePassEvent，
        由 time_pass_handler 刷新天气灵气、并让 schedule_service 挑 NPC 事件。"""

class RetreatService:
    """闭关 = 局部加速结算（README 1.6），**同步批量循环**，不是后台线程。"""
    def run(self, agent: Agent, world: WorldView, target_shichen: int) -> list[TurnResult]:
        # 1) 按 BalanceTable.cultivation_rate 分批结算 meditate，每批推进固定跨度
        # 2) 同步扣寿元：lifespan_left -= 跨度（README 2.4「闭关 100 年 = 寿元 −100」）
        # 3) 跨越潮汐日按"错过/赶上"结算一次加成，不按天重复刷
        # 4) 抽中 force 事件（走火入魔/天劫/寿元耗尽）立即中断出关
        # 5) 世界侧 NPC 不快进：出关时用时间差判定错过了哪些全局事件
        ...
```

**闭关期间 `EventArbiter` 丢弃一切非 force 投递**（§4.2），所以批量循环内不会被日程/奇遇打断。`TimeDilation` 字段保留但 MVP 恒为 1；V1 接入墙钟循环时，只改 `GameClock` 的驱动方式，`advance_for` 以下的结算路径不动。

### 4.12 event_validation：编辑器与大模型共用的校验

```python
# model/services/event_validation.py
def validate_event_def(raw: dict, ctx: "ValidationCatalog") -> tuple[GameEventDef | None, list[FieldError]]:
    """README 1.3.3 联动校验的唯一实现：
      - 谓词类型在白名单内、参数元数类型匹配
      - item_id / chain event_id / scenario_id 引用存在
      - 流程图无孤立节点与环、边不跨 scenario
      - 互斥标签不与自身冲突；变体占位符在白名单内（见 §6）
      - 金钱/境界只许走 Result 类型，不许直写字段
    """
```

**校验属于业务规则，必须放在 `services`**，由 `editor_controller`（手工保存）与 `LlmEventAuthor`（草稿生成）**共同调用同一个函数**。原设计把 `_validate_and_build` 私有在 LLM 适配器里，等于逼编辑器再写一份——两份校验一旦漂移，就退回到 README 1.3.3 明令禁止的"编辑器与运行时两套标准"。

### 4.13 其它系统服务

| 服务 | 职责 | 分期 |
|------|------|------|
| `schedule_service` | README 1.5.2：某时辰提高某标签权重，并入合格池再加权随机；抽不中即本轮无事。以 `TriggerSource=schedule` 走 `execute_occurrence`，与玩家侧同一条路径 | V1 |
| `death_service` | README 2.5：`DeathEvent` → 结算 `Biography` 碑文 → 清日程与在世标记（关系转"亡故"不删除）→ 亲友报仇/守孝事件 → 重玩三选一（转世/夺舍/继承）。**重玩换的是主角 id，不是重放存档**，故不经总线，单独用例 | V1 |
| `biography_service` | README 1.5.1：仅对同城/有未过期 `CauseLink`/被查询过的 NPC 展开细履历，步数上限 8，同样从事件库随机抽 | V1 |
| 地图回滚 | 取目标 `Occurrence.world_diff.invert()` 再 apply（§3.3.1），不需要单独的回滚表 | V1 |

---

## 5. model/repositories 层设计

### 5.1 端口定义（依赖倒置，定义在 services 里，实现在 repositories 里）

```python
# model/services/ports.py
from typing import Protocol

class EventRepository(Protocol):
    def get_by_id(self, event_id: str) -> "GameEventDef | None": ...
    def load_event_defs(self, location_type: str | None = None) -> list["GameEventDef"]: ...
    def save_event_def(self, event: "GameEventDef") -> None: ...

class ScenarioRepository(Protocol):
    """PlayTurnService 用它把 pending_scenario.scenario_id 换回图；图本身是录入产物"""
    def get(self, scenario_id: str) -> "ScenarioGraph | None": ...

class BalanceRepository(Protocol):
    def load(self, version: str | None = None) -> "BalanceTable": ...

class SnapshotStore(Protocol):
    def save_snapshot(self, world_state: dict, at: "GameTime") -> None: ...
    def load_latest_snapshot(self) -> tuple[dict, "GameTime"] | None: ...

class EventLogStore(Protocol):
    def append(self, occurrence: "GameEventOccurrence") -> None: ...
    def replay_since(self, since: "GameTime") -> list["GameEventOccurrence"]: ...

class EmbeddingPort(Protocol):
    def embed(self, text: str) -> list[float]: ...

class LlmAuthorPort(Protocol):
    """仅被 model/repositories/llm 与 controller/editor_controller.py 使用；
    model/services 对局路径（play_turn / matching / chat_parser）不持有此端口"""
    def generate_draft(self, description: str, constraints: dict) -> list["GameEventDef"]: ...
```

`services` 只依赖这些 `Protocol`，测试时可以直接用内存字典实现假对象，不需要真数据库；目录上 `ports.py` 仍放在 `services` 下（谁使用端口谁定义接口），`repositories` 只负责实现，这是依赖倒置的标准放法，不因为套了 MVC 外壳而改变。

### 5.2 SQLite 持久化（对应 1.8）

```python
# model/repositories/sqlite_event_repository.py
import sqlite3
from model.services.ports import EventRepository

class SqliteEventRepository(EventRepository):
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def load_event_defs(self, location_type=None):
        # MVP：拉全部已发布，在内存按 location_type 过滤，避免 json_each 绑死存储格式
        rows = self._conn.execute("SELECT payload FROM event_defs WHERE is_draft = 0")
        defs = [_deserialize(r[0]) for r in rows]
        if location_type is None:
            return defs
        return [e for e in defs if location_type in e.applicable_locations or "*" in e.applicable_locations]

    def save_event_def(self, event): ...
```

- **全局快照**：每游戏日对时钟 / 地点 / Agent 全量属性做快照。Agent 快照**必须含挂起字段**（`pending_encounter_id` / `pending_scenario` / `scene_focus` / `state.name`）与 `AgentEventHistory`——少一个，读档后玩家就会发现"刚才那条鱼没了"或冷却被重置。
- **增量日志**：命令段与奇遇段各写一条 `Occurrence`，JSON **必须含 `applied_diff`**；改动了地点属性的还须含 `world_diff`，否则快照之后的地图变更重放即丢。
- **读档**：`load_latest_snapshot()` → `replay_since` → 逐条 `apply_agent_diff` / `apply_world_diff`（与实时对局同一函数）。不进总线、不 matching、不跑 pipeline。缺 `applied_diff` 的旧日志视为损坏，跳过并告警。
- **随行版本**：快照记录 `balance_version` 与 `rng_seed`。前者保证旧档不被新数值表改写历史；后者只为调试复现，不参与重放正确性（重放靠 diff，不靠重掷）。

### 5.3 LlmEventAuthor（对应 1.3.4，Adapter 模式，仅录入侧）

```python
# model/repositories/llm/llm_event_author.py
from model.services.ports import LlmAuthorPort
from model.domain.events import GameEventDef

class LlmEventAuthor(LlmAuthorPort):
    def __init__(self, client, prompt_template: str, catalog: "ValidationCatalog") -> None:
        self._client = client
        self._prompt_template = prompt_template
        self._catalog = catalog

    def generate_draft(self, description: str, constraints: dict) -> list[GameEventDef]:
        raw = self._client.complete(self._prompt_template.format(description=description, **constraints))
        out = []
        for item in _parse_json_array(raw):
            # 调 §4.12 的公共校验，不在适配器里自己写一份
            defn, errors = validate_event_def(item, self._catalog)
            if defn is not None:
                out.append(replace(defn, is_draft=True))   # 一律先落草稿，人工发布才进合格池
            else:
                _report(item, errors)                       # 标错字段返给编辑器，不整体入库
        return out
```

**对局隔离**：`PlayTurnService` / `ChatParser` / `matching` 的构造函数禁止出现 `LlmAuthorPort`。该端口只注入录入用例。

---

## 6. view 层设计

`view` 只消费 `TurnResult` 与 `AppliedDiff`，禁止 import `PipelineContext`。

```python
# view/narrative_renderer.py
import string

_FORMATTER = string.Formatter()

def safe_format(text: str, placeholders: dict) -> str:
    """容错渲染：未知占位符原样保留，花括号写错不抛异常。
    渲染发生在状态已改、日志已写之后——这里抛 KeyError 会让整个回合看起来失败，
    实际却已经扣了钱。占位符白名单在录入时由 §4.12 校验，这里只兜底。"""
    try:
        return _FORMATTER.vformat(text, (), _Defaulting(placeholders))
    except Exception:
        return text

class _Defaulting(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"

def render_turn(result: "TurnResult", defs: dict[str, GameEventDef], placeholders: dict) -> str:
    if result.parse_error:
        return result.parse_error
    if result.reject_reason:
        return result.reject_reason
    parts = []
    if result.command_event_id:
        parts.append(safe_format(defs[result.command_event_id].variants[result.command_variant].text, placeholders))
    if result.encounter_event_id:
        parts.append(safe_format(defs[result.encounter_event_id].variants[result.encounter_variant].text, placeholders))
    if result.prompt_event_id:   # 挂起提示：奇遇已叙述、等玩家下一句
        parts.append(safe_format(defs[result.prompt_event_id].variants[result.prompt_variant].text, placeholders))
    return "\n".join(parts)
```

`StateDiffView.from_applied_diff(diff: AppliedDiff)`。万年历 `render_calendar_plaque` 不变。DTO 仍只做字段形状，校验在 model。

---

## 7. controller 层（薄入口）

```python
# controller/chat_controller.py
def on_player_message(raw_text: str, agent_id: str) -> str:
    agent = agent_repo.load(agent_id)
    world = world_repo.assemble_view()
    result = play_turn.handle_player_text(agent, world, raw_text)
    agent_repo.save(agent)
    return narrative_renderer.render_turn(result, event_index, placeholders_from(agent))
```

controller 不调用 arbiter / pipeline / matching。编辑器 controller 只编排保存定义、`LlmEventAuthor`、模拟沙盒。

---

## 8. 设计模式落点速查表

| 模式 | 落点 | README 对应节 |
|------|------|------|
| 观察者 | `model/services/event_bus.py` | 3.1 |
| 责任链 | `model/services/pipeline.py` | 3.6 |
| 策略 | `model/services/handlers/*` | 3.2 |
| 状态 | `model/domain/states.py` | 3.3 |
| 工厂 | `model/services/registry.py` | 3.4 |
| 插件 | `model/services/plugin_loader.py` | 3.5 |
| 端口/适配器（依赖倒置） | `model/services/ports.py` + `model/repositories/*` | 隐含于 1.1 分层要求 |
| 用例 | `model/services/play_turn.py` | README 2.2 两段循环 |
| 命令/差分（Command-Diff） | `model/domain/diff.py`：结果只产 diff，apply 是唯一写入点 | 1.8 Event Sourcing |
| 薄入口 + 渲染 | `controller/*` / `view/*` | 本文档 |

---

## 9. 测试策略分层（对应 3.7 单测最小集）

- **`tests/model/domain`**：`Predicate.evaluate`、`PredicateGroup` 的 AND/OR 组合、`AgentState.try_transition` 拒绝非法指令、`GameTime` 加减——纯函数，不 mock。
- **`tests/model/services`**：内存假仓库 + 固定 `rng`：
  - `PlayTurnService`：谓词失败则状态仍为 idle、不写日志、**不产 diff**；两段都 `append`；`needs_reply` 进入 EncounterPending
  - **挂起结算**：EncounterPending 时「买下来」走局部选项而非全局别名；说无关的话则挂起项按错过清空且不残留悬空 id；流程图跨回合推进后 `pending_scenario` 正确前移、终点清空
  - **事务性**：`ResultPoolExecutor` 中途抛异常时 Agent 字段一个都没变（apply 未执行）
  - 总线延后投递：handler 内 publish 不重入当前 handler；连锁事件在 apply 之后才投递
  - 仲裁：dead 丢弃、闭关非 force 丢弃、acting 时 encounter **入队且不执行结果池**（回归项：曾把 ENQUEUE 当 EXECUTE）
  - 粗筛硬过滤：冷却期内、次数用尽、互斥标签冲突的事件**完全不出现在合格池**，而不是权重变低
  - `pick_variant` 不连续重复同一条文案；`reweight_and_pick` 长尾分布
  - Registry 未知 type 跳过；ValidationStep 失败不写因果
  - `RetreatService`：闭关跨度与寿元扣减一致；跨潮汐只结算一次；抽中 force 立即出关
- **`tests/model/repositories`**：`:memory:` SQLite：快照 + 只重放 `applied_diff` / `world_diff` 后与当时 Agent 和地图一致（**含挂起字段与 `AgentEventHistory`**）；缺 diff 的日志被跳过。`LlmEventAuthor` 假 client 校验失败不入库。
- **`tests/model/domain`（补）**：`apply_agent_diff` 与 `merge` 的可交换性；`WorldDiff.invert()` 往返后地图属性还原。
- **`tests/view`**：`render_turn` 只根据 `TurnResult`，不构造 pipeline；`safe_format` 遇未知占位符/畸形花括号不抛异常。
- **`tests/controller`**：mock `PlayTurnService`，断言只调一次 `handle_player_text`；编辑器路径草稿不进 `get_by_id` 对局池。
- **架构守卫测试**（值得单列一个 `tests/test_layering.py`）：用 `ast` 扫源码，断言 `model/domain/**` 不 import `model/repositories`、`view`、`sqlite3`；`play_turn.py` / `matching.py` / `chat_parser.py` 的源码中不出现 `LlmAuthorPort`；`controller/**` 不 import `pipeline` / `matching` / `arbiter`。这几条约束靠人工代码审查守不住，写成测试才有效。

---

## 10. 技术选型说明

- **Python 3.11+**：使用 `X | Y` 联合类型语法、`slots=True` dataclass 降低内存开销（长履历/大量 NPC 场景）。
- **持久化**：标准库 `sqlite3`，不引入 SQLAlchemy ORM——领域对象保持贫血模型，序列化/反序列化显式写在 `model/repositories` 里，便于 Event Sourcing 逐条重放时精确控制。
- **对外 API**（V1+ 需要真正的聊天前端/编辑器前端时）：建议 FastAPI，路由文件放在 `controller/` 下；如果用 Pydantic 定义请求/响应模型，放在 `view/schemas/`，并在 `controller` 层完成 Pydantic 模型 ↔ `model.domain` dataclass 的转换，`model` 包本身不 import `pydantic`，保持业务层框架无关。
- **依赖注入**：构造函数手动注入。对局侧签名上看不到 `LlmAuthorPort`。
- **单线程**：MVP 单线程、回合驱动（§1 时间模型决策）；总线队列不跨线程，不必上锁。V1 若接入墙钟循环，改的是 `GameClock` 的驱动方式，`advance_for` 以下不动。

---

## 11. 实现期 TODO（已知未决，不阻塞开工）

| # | 事项 | 说明 |
|---|------|------|
| 1 | `ChatParser` 的匹配策略 | MVP 是精确别名表。同义词多了会退化成"必须背咒语"，V2 上向量匹配前需要一版别名覆盖率统计 |
| 2 | `AgentEventHistory` 的窗口裁剪 | `triggers` 按 event_id 无限追加会随游戏年数膨胀。需定一个保留策略（按最近 N 条 + 最长冷却时长取大） |
| 3 | `merge(AppliedDiff)` 的冲突语义 | 同一回合两条 `realm_set` 或 `location_set` 谁赢，需明确（建议后写覆盖，并在录入校验时告警） |
| 4 | 快照频率 | "每游戏日"在闭关批量结算时会瞬间生成大量快照。闭关期间应改为按结算批次而非游戏日 |
| 5 | `WorldView.mutable_state()` 的边界 | 目前 `ApplyDiffStep` 通过它写世界状态，与"WorldView 只读"的表述有张力，实现时应拆成 `WorldView`（读）+ `WorldState`（写） |
| 6 | 天劫窗口 | README 2.3.1 说日历可推算窗口但仍随机。窗口只影响 `applicable_time` 粗筛，不做预约队列——实现时注意别写成定时器 |
| 7 | NPC 规模 | 全量 NPC 都跑日程会随世界变大而变慢。1.5.1 的"仅同城/有因果/被查询过"预算规则需要在 `schedule_service` 里落成硬上限 |
