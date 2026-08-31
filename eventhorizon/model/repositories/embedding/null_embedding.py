"""model/repositories/embedding/null_embedding.py — MVP：向量模块关闭时的空实现
（对应 README 1.4.1）。

MVP 可关闭本模块，事件只走元数据过滤 + 权重随机。NullEmbeddingService 让依赖
EmbeddingPort 的代码（去重、V2 新颖度重排）在关闭向量检索时也能正常跑，只是永远
拿到零向量/永远判定"不相似"。
"""
from __future__ import annotations


class NullEmbeddingService:
    def embed(self, text: str) -> list[float]:
        return []
