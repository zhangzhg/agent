import unittest
from unittest.mock import patch

from model.services.local_embedding import (
    LOCAL_EMBEDDING_DIMS,
    FallbackEmbeddingClient,
    embed_with_fallback,
    local_embed,
)


class _FakeEmbeddingClient:
    def __init__(self, vector=None, raises=False):
        self._vector = vector
        self._raises = raises

    def embed(self, text):
        if self._raises:
            raise RuntimeError("模拟网络失败")
        return self._vector


def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class LocalEmbedTests(unittest.TestCase):
    def test_same_text_produces_identical_vector(self):
        self.assertEqual(local_embed("一把锋利的长剑"), local_embed("一把锋利的长剑"))

    def test_vector_has_configured_dimensionality(self):
        self.assertEqual(len(local_embed("随便什么文字")), LOCAL_EMBEDDING_DIMS)

    def test_empty_text_returns_all_zero_vector(self):
        vec = local_embed("   ")
        self.assertEqual(vec, tuple(0.0 for _ in range(LOCAL_EMBEDDING_DIMS)))

    def test_vector_is_l2_normalized(self):
        vec = local_embed("一把锋利的长剑")
        norm = sum(v * v for v in vec) ** 0.5
        self.assertAlmostEqual(norm, 1.0, places=6)

    def test_related_texts_are_more_similar_than_unrelated(self):
        sword = local_embed("一把锋利的长剑")
        old_sword = local_embed("一把布满锈迹的古老长剑")
        pill = local_embed("一颗温补的丹药")
        self.assertGreater(_cosine(sword, old_sword), _cosine(sword, pill))

    def test_custom_dims_is_respected(self):
        self.assertEqual(len(local_embed("text", dims=16)), 16)


class EmbedWithFallbackTests(unittest.TestCase):
    """三层兜底链：client（一般是 GLM） -> 本地真实模型（bge） -> 字符哈希。
    单测里用假的 bge 客户端替换掉真实模型加载（monkeypatch `_get_bge_client`），
    不然每条用例都要真的跑一遍深度学习模型，既慢又依赖网络/本机缓存。"""

    def test_successful_client_result_is_used_verbatim(self):
        client = _FakeEmbeddingClient(vector=[0.1, 0.2, 0.3])
        result = embed_with_fallback(client, "一把锋利的长剑")
        self.assertEqual(result, (0.1, 0.2, 0.3))

    def test_none_client_falls_back_to_bge_tier(self):
        with patch("model.services.local_embedding._get_bge_client") as get_bge:
            get_bge.return_value = _FakeEmbeddingClient(vector=[9.0, 9.0])
            result = embed_with_fallback(None, "一把锋利的长剑")
        self.assertEqual(result, (9.0, 9.0))

    def test_client_exception_falls_back_to_bge_tier(self):
        client = _FakeEmbeddingClient(raises=True)
        with patch("model.services.local_embedding._get_bge_client") as get_bge:
            get_bge.return_value = _FakeEmbeddingClient(vector=[9.0, 9.0])
            result = embed_with_fallback(client, "一把锋利的长剑")
        self.assertEqual(result, (9.0, 9.0))

    def test_client_empty_result_falls_back_to_bge_tier(self):
        client = _FakeEmbeddingClient(vector=[])
        with patch("model.services.local_embedding._get_bge_client") as get_bge:
            get_bge.return_value = _FakeEmbeddingClient(vector=[9.0, 9.0])
            result = embed_with_fallback(client, "一把锋利的长剑")
        self.assertEqual(result, (9.0, 9.0))

    def test_bge_tier_exception_falls_back_to_local_hash(self):
        """client 为 None、bge 本地模型也不可用（缺依赖/加载失败等环境问题）——
        兜底的兜底，字符哈希，恒不失败。"""
        with patch("model.services.local_embedding._get_bge_client") as get_bge:
            get_bge.return_value = _FakeEmbeddingClient(raises=True)
            result = embed_with_fallback(None, "一把锋利的长剑")
        self.assertEqual(result, local_embed("一把锋利的长剑"))

    def test_bge_tier_empty_result_falls_back_to_local_hash(self):
        with patch("model.services.local_embedding._get_bge_client") as get_bge:
            get_bge.return_value = _FakeEmbeddingClient(vector=[])
            result = embed_with_fallback(None, "一把锋利的长剑")
        self.assertEqual(result, local_embed("一把锋利的长剑"))


class FallbackEmbeddingClientTests(unittest.TestCase):
    """生产环境的统一入口——包装三层兜底链，本身实现 EmbeddingPort，永远不是 None。"""

    def test_delegates_to_embed_with_fallback(self):
        client = FallbackEmbeddingClient(_FakeEmbeddingClient(vector=[1.0, 2.0]))
        self.assertEqual(client.embed("测试文本"), [1.0, 2.0])

    def test_none_primary_still_returns_a_usable_vector(self):
        client = FallbackEmbeddingClient(None)
        with patch("model.services.local_embedding._get_bge_client") as get_bge:
            get_bge.return_value = _FakeEmbeddingClient(vector=[3.0, 4.0])
            self.assertEqual(client.embed("测试文本"), [3.0, 4.0])


if __name__ == "__main__":
    unittest.main()
