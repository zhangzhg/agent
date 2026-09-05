import unittest

from model.services.local_embedding import LOCAL_EMBEDDING_DIMS, embed_with_fallback, local_embed


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
    def test_none_client_falls_back_to_local(self):
        result = embed_with_fallback(None, "一把锋利的长剑")
        self.assertEqual(result, local_embed("一把锋利的长剑"))

    def test_client_exception_falls_back_to_local(self):
        client = _FakeEmbeddingClient(raises=True)
        result = embed_with_fallback(client, "一把锋利的长剑")
        self.assertEqual(result, local_embed("一把锋利的长剑"))

    def test_client_empty_result_falls_back_to_local(self):
        client = _FakeEmbeddingClient(vector=[])
        result = embed_with_fallback(client, "一把锋利的长剑")
        self.assertEqual(result, local_embed("一把锋利的长剑"))

    def test_successful_client_result_is_used_verbatim(self):
        client = _FakeEmbeddingClient(vector=[0.1, 0.2, 0.3])
        result = embed_with_fallback(client, "一把锋利的长剑")
        self.assertEqual(result, (0.1, 0.2, 0.3))


if __name__ == "__main__":
    unittest.main()
