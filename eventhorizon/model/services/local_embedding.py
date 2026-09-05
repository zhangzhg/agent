"""model/services/local_embedding.py — 本地兜底向量化：LLM 向量化不可用（没配置
embedding_model，或调用失败——网络问题、账户余额不足等）时的退路，不需要网络/
大模型，纯本地计算。

用字符 + 字符二元组的哈希词袋近似语义相似度：两段文字共享的字/词越多，向量
夹角越小。精度远不如真实 embedding 模型（分不出"意思相近但没有共同字"的情况，
比如"长剑"跟"兵刃"），但至少能分辨"完全不沾边" vs "明显相关"，比 embedding
调用失败时干脆放弃匹配更有用。

维度（LOCAL_EMBEDDING_DIMS=128）刻意跟常见真实 embedding 模型的维度
（1024/1536/2048…）区分开——真实向量和本地向量长度不同，
model/services/matching.py 的 cosine_similarity() 见到长度不一致会直接判 0，
不会把"一个真向量、一个本地凑的向量"误判成有意义的相似度，是有意的"宁可判不
匹配，不要判假匹配"。

哈希用手写的确定性滚动哈希，不用内置 hash()——内置 hash() 对字符串按进程随机化
（PYTHONHASHSEED），同一段文字在不同进程（比如重启服务）里会编出不同的向量，
存下来的向量后续就没法比对了。
"""
from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from model.services.ports import EmbeddingPort

_logger = logging.getLogger("eventhorizon.local_embedding")

LOCAL_EMBEDDING_DIMS = 128


def _stable_hash(token: str) -> int:
    h = 0
    for ch in token:
        h = (h * 131 + ord(ch)) & 0xFFFFFFFF
    return h


def local_embed(text: str, dims: int = LOCAL_EMBEDDING_DIMS) -> tuple[float, ...]:
    """字符+字符二元组哈希词袋，L2 归一化。空文本返回全零向量（跟任何向量的
    cosine_similarity 都是 0，天然"不匹配"，不用另外特判）。"""
    chars = [c for c in text.strip() if not c.isspace()]
    if not chars:
        return tuple(0.0 for _ in range(dims))
    tokens = list(chars) + [a + b for a, b in zip(chars, chars[1:])]
    vec = [0.0] * dims
    for tok in tokens:
        vec[_stable_hash(tok) % dims] += 1.0
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0.0:
        return tuple(vec)
    return tuple(v / norm for v in vec)


def embed_with_fallback(client: "EmbeddingPort | None", text: str) -> tuple[float, ...]:
    """所有需要向量化的地方统一走这个函数，不要直接调 client.embed()：先试真实
    LLM 向量化，client 为 None（没配置）或调用失败（网络/账户余额等）都退到
    local_embed()——只要文字本身非空，永远能拿到一个可用于比较的向量，不会因为
    embedding 服务不可用就让 predicate_text/物品匹配这类功能整个失效。"""
    if client is not None:
        try:
            vec = client.embed(text)
            if vec:
                return tuple(vec)
        except Exception as exc:
            _logger.warning("LLM 向量化失败，退回本地向量化：%s", exc)
    return local_embed(text)
