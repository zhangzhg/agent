"""view/inventory_panel_view.py — 背包面板（GAME_DESIGN §2.6）。

简单堆叠列表：图标 + 名称 + 数量，点击查看物品描述（只读 tooltip）。使用/丢弃
物品仍靠聊天，面板不放"使用"按钮——这里只产出展示数据，没有任何动作字段。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from model.domain.agent import Agent
    from model.services.ports import ItemRepository


@dataclass
class InventoryRow:
    item_id: str
    name: str
    count: int
    description: str


@dataclass
class InventoryPanel:
    rows: list[InventoryRow] = field(default_factory=list)
    total_count: int = 0


def build_inventory_panel(agent: "Agent", items: "ItemRepository") -> InventoryPanel:
    rows = []
    for item_id, count in sorted(agent.inventory.counts.items()):
        item_def = items.get_by_id(item_id)
        rows.append(
            InventoryRow(
                item_id=item_id,
                name=item_def.name if item_def and item_def.name else item_id,
                count=count,
                description=item_def.description if item_def else "",
            )
        )
    return InventoryPanel(rows=rows, total_count=sum(agent.inventory.counts.values()))
