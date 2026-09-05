import unittest

from model.domain.items import ItemDef, ItemKind
from model.services.item_embedding_match import (
    ITEM_MATCH_LOCAL_SIMILARITY_THRESHOLD,
    ITEM_MATCH_SIMILARITY_THRESHOLD,
    find_best_matching_item,
)
from model.services.local_embedding import LOCAL_EMBEDDING_DIMS, local_embed


def _item(item_id, embedding=(), kind=ItemKind.GEAR):
    return ItemDef(item_id=item_id, kind=kind, name=item_id, embedding=embedding)


class FindBestMatchingItemTests(unittest.TestCase):
    def test_finds_closest_match_above_threshold(self):
        items = [
            _item("sword", embedding=(1.0, 0.0)),
            _item("pill", embedding=(0.0, 1.0)),
        ]
        result = find_best_matching_item(items, query_embedding=(1.0, 0.0), threshold=0.5)
        self.assertEqual(result.item_id, "sword")

    def test_no_match_above_threshold_returns_none(self):
        items = [_item("sword", embedding=(1.0, 0.0))]
        result = find_best_matching_item(items, query_embedding=(0.0, 1.0), threshold=0.5)
        self.assertIsNone(result)

    def test_empty_query_embedding_returns_none(self):
        items = [_item("sword", embedding=(1.0, 0.0))]
        self.assertIsNone(find_best_matching_item(items, query_embedding=(), threshold=0.5))

    def test_items_without_embedding_are_skipped(self):
        items = [_item("no_embedding", embedding=())]
        self.assertIsNone(find_best_matching_item(items, query_embedding=(1.0, 0.0), threshold=0.5))

    def test_empty_item_list_returns_none(self):
        self.assertIsNone(find_best_matching_item([], query_embedding=(1.0, 0.0), threshold=0.5))

    def test_picks_the_single_best_match_not_just_first_above_threshold(self):
        items = [
            _item("close_enough", embedding=(0.9, 0.1)),
            _item("best_match", embedding=(1.0, 0.0)),
        ]
        result = find_best_matching_item(items, query_embedding=(1.0, 0.0), threshold=0.5)
        self.assertEqual(result.item_id, "best_match")


class ThresholdAutoDetectionTests(unittest.TestCase):
    """threshold 不显式传时，按向量维度自动选阈值：真实向量（非 128 维）走
    ITEM_MATCH_SIMILARITY_THRESHOLD（严格），本地兜底向量（128 维）走
    ITEM_MATCH_LOCAL_SIMILARITY_THRESHOLD（宽松）——不然本地向量永远打不过真实
    向量的阈值。"""

    def test_real_dimension_vector_uses_strict_default_threshold(self):
        items = [_item("sword", embedding=(1.0, 0.0))]
        # 余弦相似度 0.5（低于 ITEM_MATCH_SIMILARITY_THRESHOLD=0.8，高于
        # ITEM_MATCH_LOCAL_SIMILARITY_THRESHOLD=0.2）——只有真的套用了严格档
        # 才会判不匹配，验证 2 维（非本地维度）走的是默认阈值而非本地阈值。
        below = (0.5, (1 - 0.5 * 0.5) ** 0.5)
        self.assertIsNone(find_best_matching_item(items, query_embedding=below))

    def test_local_dimension_vector_uses_lenient_local_threshold(self):
        real_embedding = local_embed("一把布满锈迹的古老长剑")
        items = [_item("sword", embedding=real_embedding)]
        query = local_embed("一把锋利的长剑")
        self.assertEqual(len(query), LOCAL_EMBEDDING_DIMS)
        result = find_best_matching_item(items, query_embedding=query)
        self.assertEqual(result.item_id, "sword")

    def test_local_dimension_vector_below_local_threshold_returns_none(self):
        # 跟"锋利的长剑"没有共享字符（不像"一颗温补的丹药"那样共享"一/的"这类
        # 高频虚词，会把相似度顶到刚好越过阈值——本地词袋对虚词没有区分度，
        # 挑选测试文本时要避开这个假阳性来源）。
        items = [_item("pill", embedding=local_embed("一颗培元丹"))]
        query = local_embed("一把锋利的长剑")
        self.assertIsNone(find_best_matching_item(items, query_embedding=query))

    def test_mismatched_dimensions_never_cross_match(self):
        # item 向量是"真实" 2 维，query 是本地 128 维——cosine_similarity 因长度
        # 不一致直接判 0，不会被本地宽松阈值误判成匹配。
        items = [_item("sword", embedding=(1.0, 0.0))]
        query = local_embed("sword")
        self.assertIsNone(find_best_matching_item(items, query_embedding=query))

    def test_explicit_threshold_overrides_auto_detection(self):
        # 相关但不完全相同的一对文本，相似度落在本地默认阈值（0.2）之上、
        # 但达不到显式传入的严格阈值（0.99）——验证显式 threshold 真的生效，
        # 而不是被自动判维度的逻辑覆盖掉。
        items = [_item("sword", embedding=local_embed("一把布满锈迹的古老长剑"))]
        query = local_embed("一把锋利的长剑")
        self.assertIsNone(find_best_matching_item(items, query_embedding=query, threshold=0.99))


if __name__ == "__main__":
    unittest.main()
