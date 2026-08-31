"""content/items.py — 物品定义（供背包面板展示，GAME_DESIGN §2.6）。"""
from __future__ import annotations

from model.domain.items import ItemDef, ItemKind

ALL = (
    ItemDef("dragon_scale", ItemKind.MATERIAL, name="龙鳞", description="温润泛光的一片鳞甲，来历不凡。"),
    ItemDef("spirit_herb", ItemKind.MATERIAL, name="灵草", description="带着一丝灵气的草药，可入丹方。"),
    ItemDef("cloth_pouch", ItemKind.MATERIAL, name="布袋", description="一个普通的小布袋，能装些零碎物件。"),
    ItemDef("basic_manual", ItemKind.MANUAL, unique=True, name="基础功法残卷", description="残缺不全，但仍可参详一二。"),
    ItemDef("ancient_token", ItemKind.MATERIAL, unique=True, name="古老令牌", description="不知年岁的令牌，似乎还有余韵未散。"),
    ItemDef("gold", ItemKind.MATERIAL, name="金饰", description="成色不错的黄金饰品。"),
)
