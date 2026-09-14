"""model/domain/events.py — 事件（对应 README 1.3.2 / 1.4.3）。

GameEventDef 与 Occurrence 分离。日志必须带 applied_diff（世界级变更另带
world_diff）：录入日后改结果池，旧档仍按当时差分重放。读档 = 快照 + 逐条 apply
diff，禁止对历史再跑 matching / 责任链。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from model.domain.predicates import PredicateGroup

if TYPE_CHECKING:
    from model.domain.diff import AppliedDiff, WorldDiff
    from model.domain.results import Result
    from model.domain.time import GameTime


# LiveContentAuthor 对局中实时创作的事件，event_id 一律以此开头（README §1.12）。
# 它同时是这类事件的"来源标记"：录入编辑器靠它把玩家碎碎念产生的内容跟手工内容
# 区分开，仓库靠它做容量回收（见 EventRepository.prune_live_events）。放在 domain
# 只是因为它是一条 id 命名约定，创建方（services）和回收方（repositories）都要用，
# 不适合塞进任何一边。
LIVE_EVENT_ID_PREFIX = "live_"


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
    response_text: str = ""  # 这条选项本身的应答文案（如"你付了钱，鱼贩笑呵呵地把
    # 鱼包好递给你"）；宿主事件的 GameEventDef.variants 是"奇遇发生时"的叙述，不是
    # "选了这个选项"的叙述，两者不能共用同一份文案，否则玩家会看到同一句话重复两遍。


@dataclass(frozen=True, slots=True)
class GameEventDef:
    """事件库中的一条定义（录入产物），不可变；运行时不修改它。"""

    event_id: str
    applicable_locations: tuple[str, ...]
    applicable_time: tuple[int, ...] | None
    predicate: PredicateGroup | None
    weight: float
    duration_shichen: int  # README 核心诉求 2「持续时间」：时间推进的唯一来源
    cooldown_shichen: int
    max_trigger_per_agent: int | None
    exclusive_tags: tuple[str, ...]
    priority: int  # 仲裁默认等级，被 TriggerSource 覆盖（README 1.7）
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
    description: str = ""
    # 给管理员看的简短说明（"这条事件是干什么的"），跟 item/location 已有的
    # description 字段是同一个定位——纯粹是录入编辑器事件列表/表单里的备注，
    # 不喂给玩家、不参与判定；跟 predicate_text（触发条件）、result_text（结果）、
    # variants（玩家看到的叙事文案）都是不同的东西，别混着填。

    predicate_text: str = ""
    # 自然语言触发条件（用户显式选择：用向量相似度比较代替结构化谓词比较，接受
    # 模糊匹配的代价——见 README 1.4.1 原本"补盲区、不替代规则"的定位，这里是一次
    # 有意识的偏离）。跟 predicate 互不冲突：predicate 非空时优先按它做精确判定
    # （硬条件，如 money_gte 这类不能模糊的），predicate 为空且 predicate_text 非空
    # 时才走 matching.py 里的向量相似度判定；两个都空 = 无条件。
    predicate_embedding: tuple[float, ...] = ()
    # 录入（保存）时用 EmbeddingPort 预计算并缓存，不在每次触发时现场编码
    # predicate_text（README 1.4.1："事件 embedding 在录入时预计算并缓存"）。

    result_text: str = ""
    # 自然语言的"结果"描述（编辑器用它替代手填 result_pool JSON）。保存时若能解析
    # 出明确的数值得失，会同步写进 result_pool 参与真实结算；result_text 本身只是
    # 给人看的描述，不参与运行时判定——跟 predicate_text 不同，没有对应的"运行时
    # 用文字本身做判断"的机制。

    narrative_embedding: tuple[float, ...] = ()
    # 事件"在讲什么"的向量表示（tags+aliases+variants 文案拼接后录入时预计算），
    # 用于 model/services/matching.py 的叙事贴切度重排——回答的是"这个事件此刻讲不
    # 讲得通"，跟 predicate_embedding 回答的"触发条件是否成立"是两个不同的问题，
    # 不共用同一份向量（见《向量化.md》"第二阶段：向量语义匹配"）。只做候选之间的
    # 软加权，不做硬过滤——两边向量任一缺失就是中性乘子 1.0，不影响谁能不能触发。

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
