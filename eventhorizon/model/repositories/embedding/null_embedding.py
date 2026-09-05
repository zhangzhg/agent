"""model/repositories/embedding/null_embedding.py — EmbeddingPort 的空实现：向量
模块关闭（没配置 embedding_model，或干脆不想接真实向量服务）时用这个。

跟"MVP 可关闭本模块，事件只走元数据过滤 + 权重随机"（README 1.4.1）的原则一致：
返回空向量，model/services/matching.py 见到空向量就把 predicate_text 当成"无条件"
处理（fail-open）——模块关闭时应该表现得像它从未存在过，而不是让写了自然语言条件
的事件全部卡死打不出来（那样反而比没有这个功能更糟：内容作者会看到一堆"写了却
永远不触发"的死草稿，还不知道是为什么）。
"""
from __future__ import annotations


class NullEmbeddingService:
    def embed(self, text: str) -> list[float]:
        return []
