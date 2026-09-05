"""model/domain/items.py — 物品与背包（对应 README 1.10）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ItemKind(str, Enum):
    FOOD = "food"
    PILL = "pill"
    MANUAL = "manual"
    MATERIAL = "material"
    GEAR = "gear"


@dataclass(frozen=True, slots=True)
class ItemDef:
    item_id: str
    kind: ItemKind
    stackable: bool = True
    unique: bool = False
    name: str = ""
    description: str = ""  # 背包面板"点击查看物品描述"用（GAME_DESIGN §2.6）
    embedding: tuple[float, ...] = ()
    # name+description 的向量，录入（保存物品）时预计算并缓存——事件"结果"文字描述
    # 提到"获得某样东西"时，拿这个跟描述的向量比对，找出语义最接近的真实物品
    # （model/services/item_embedding_match.py），而不是让 AI 自己编一个 item_id
    # （十有八九是悬空引用）。跟 predicate_embedding 一样，只在录入时算一次，不在
    # 每次触发时现场编码全库。


@dataclass(slots=True)
class Inventory:
    counts: dict[str, int] = field(default_factory=dict)

    def has(self, item_id: str, n: int = 1) -> bool:
        return self.counts.get(item_id, 0) >= n

    def add(self, item_id: str, n: int = 1) -> None:
        self.counts[item_id] = self.counts.get(item_id, 0) + n

    def consume(self, item_id: str, n: int = 1) -> bool:
        if not self.has(item_id, n):
            return False
        remaining = self.counts[item_id] - n
        if remaining <= 0:
            del self.counts[item_id]
        else:
            self.counts[item_id] = remaining
        return True
