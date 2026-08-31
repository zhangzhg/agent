"""model/domain/balance.py — 数值集中配置（对应 README 2.4）。

README 2.4 的数值骨架，集中配置便于调优。Check 执行器按 kind 读这里，
公式里不出现具体物品名或事件 id。以 JSON/TOML 随存档版本一起分发。
"""
from __future__ import annotations

from dataclasses import dataclass, field


DEFAULT_REALM_ORDER: tuple[str, ...] = ("凡人", "练气", "筑基", "金丹", "元婴", "化神", "渡劫", "大乘", "仙人")
"""境界链有序常量（README 2.4），供 EvalContext.realm_rank() 在没有注入 BalanceTable
时也能比较境界。BalanceTable.realm_order 默认取同一份数据，避免境界顺序两处各写一份。"""


def _default_realm_order() -> tuple[str, ...]:
    return DEFAULT_REALM_ORDER


def _default_breakthrough() -> dict[str, float]:
    """GAME_DESIGN §7.2：P(突破) = clamp(资质×灵气浓度×丹药加成 − 心魔 − 境界惩罚, 0.05, 0.95)。
    示例代入（练气三层→四层，资质1.0，灵气浓度0.4，无丹药，心魔0.1，境界惩罚0.05）
    应得 P=0.25——result_pool_executor._breakthrough_probability 按这份配置复算即得此数。"""
    return {
        "pill_bonus_baseline": 1.0,  # 无丹药时的乘数基线；丹药 buff 系统留待 V1+
        "realm_penalty_weight": 0.05,  # 境界惩罚 = 该值 × realm_rank
        "clamp_min": 0.05,
        "clamp_max": 0.95,
        "fail_setback_ratio": 0.2,  # 失败后修为回退比例（§7.2："修为回退 20%"）
        "fail_heart_demon_gain": 0.05,  # 失败后心魔增量（§7.2："心魔 +0.05"）
        "consecutive_fail_threshold": 3,  # 连续失败达此次数触发走火入魔（§7.2）
        "qi_deviation_event_id": "qi_deviation",  # content 侧需定义同名 force 事件
    }


def _default_combat() -> dict[str, float]:
    """GAME_DESIGN §7.3：P(胜) = clamp(境界差 + 道具 + 运势 − 心魔, 0.05, 0.95)，
    境界差按"每高一级 +0.15，每低一级 -0.15"换算。装备加成留待 V1+ 装备系统，
    当前恒为 0；示例（同境界、+0.1 道具、运势基线、心魔 0.05）应得 P=0.55。"""
    return {
        "realm_gap_weight": 0.15,
        "gear_bonus": 0.0,  # 无装备系统时的占位值
        "luck_scale": 1.0,  # 运势直接读 Agent.luck，此为换算系数
        "clamp_min": 0.05,
        "clamp_max": 0.95,
    }


def _default_cultivation_rate() -> dict[str, float]:
    return {"base_per_shichen": 1.0, "aptitude_weight": 1.0, "qi_density_weight": 1.0, "tidal_multiplier": 1.5}


def _default_cultivation_required() -> dict[str, float]:
    """突破所需修为（GAME_DESIGN §7.1"修为需求"列）。练气按"每层 100 × 九层"折算
    总量：本引擎的 realm_order 不建模子层，Agent.cultivation 连续累加，练气内部第几层
    由 view 层按 cultivation // 100 近似展示（见 view/character_panel_view.py）。"""
    return {
        "练气": 900.0,
        "筑基": 1500.0,
        "金丹": 4000.0,
        "元婴": 10000.0,
        "化神": 25000.0,
        "渡劫": 50000.0,
        "大乘": 100000.0,
    }


def _default_lifespan_by_realm() -> dict[str, float]:
    return {
        "凡人": 80.0,
        "练气": 120.0,
        "筑基": 200.0,
        "金丹": 350.0,
        "元婴": 600.0,
        "化神": 1000.0,
        "渡劫": 1500.0,
        "大乘": 3000.0,
        "仙人": 999999.0,  # 叙事性终局，非数值上限（GAME_DESIGN §7.1）
    }


@dataclass(frozen=True, slots=True)
class BalanceTable:
    realm_order: tuple[str, ...] = field(default_factory=_default_realm_order)
    breakthrough: dict[str, float | str] = field(default_factory=_default_breakthrough)  # 混入 qi_deviation_event_id
    combat: dict[str, float] = field(default_factory=_default_combat)
    cultivation_rate: dict[str, float] = field(default_factory=_default_cultivation_rate)
    cultivation_required: dict[str, float] = field(default_factory=_default_cultivation_required)
    lifespan_by_realm: dict[str, float] = field(default_factory=_default_lifespan_by_realm)
    version: str = "v1"

    def realm_rank(self, realm: str) -> int:
        return self.realm_order.index(realm)

    def next_realm(self, realm: str) -> str | None:
        rank = self.realm_rank(realm)
        if rank + 1 >= len(self.realm_order):
            return None
        return self.realm_order[rank + 1]

    def cultivation_required_for(self, realm: str) -> float | None:
        """突破出 realm 所需的修为总量；凡人/仙人没有数值门槛（前者靠年龄，后者是终局）。"""
        return self.cultivation_required.get(realm)


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))
