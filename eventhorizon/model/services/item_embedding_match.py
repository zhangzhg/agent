"""model/services/item_embedding_match.py — 用向量相似度在物品库里找"语义上最像"
的真实物品（对应事件"结果"文字描述提到"获得/得到某样东西"时的物品解析）。

只在录入（保存事件）时跑一次，不在对局触发时现场跑——物品库不大、结果也已经
预先解析好写进 result_pool 里的 item_drop 了，触发时就是一条普通的精确 ItemDrop，
跟手工录入的没有区别（README 1.4.1 的"预计算并缓存"原则）。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from model.services.local_embedding import LOCAL_EMBEDDING_DIMS
from model.services.matching import cosine_similarity

if TYPE_CHECKING:
    from model.domain.items import ItemDef

# 凭经验给的起始阈值，没有实测数据支撑——物品匹配错了比谓词判定错了后果更直接
# （直接塞一个不相关的东西进背包），所以起点定得比 predicate 那边更严格一些；
# 接入真实 embedding 模型后应该按实际相似度分布重新标定。
ITEM_MATCH_SIMILARITY_THRESHOLD = 0.8

# 本地兜底向量（model/services/local_embedding.py）是字符/字符二元组的哈希词袋，
# 相似度的量纲跟真实 embedding 完全不同——实测"一把锋利的长剑" vs 明显相关的
# "一把布满锈迹的古老长剑"只有 ~0.45，vs 明显无关的"一颗培元丹"只有 ~0.07。用
# 真实向量的阈值（0.8）套本地向量，等于永远匹配不上，所以本地向量走一个单独
# 标定过的、低得多的阈值。
ITEM_MATCH_LOCAL_SIMILARITY_THRESHOLD = 0.2


def find_best_matching_item(
    items: list["ItemDef"], query_embedding: tuple[float, ...], threshold: float | None = None
) -> "ItemDef | None":
    """items 和 query_embedding 任一没有可用向量都返回 None（fail-closed——找不到
    匹配就是不发物品，比乱发一个不相关的东西安全）。threshold 不显式传时，按
    query_embedding 的维度自动判断是真实向量还是本地兜底向量、套对应的阈值——
    维度不同的 item 向量会被 cosine_similarity 自然判 0（不会拿真实向量硬套本地
    向量的阈值，反之亦然）。"""
    if not query_embedding:
        return None
    if threshold is None:
        threshold = (
            ITEM_MATCH_LOCAL_SIMILARITY_THRESHOLD
            if len(query_embedding) == LOCAL_EMBEDDING_DIMS
            else ITEM_MATCH_SIMILARITY_THRESHOLD
        )
    best: "ItemDef | None" = None
    best_score = threshold
    for item in items:
        if not item.embedding:
            continue
        score = cosine_similarity(query_embedding, item.embedding)
        if score >= best_score:
            best = item
            best_score = score
    return best
