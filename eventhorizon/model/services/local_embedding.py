"""model/services/local_embedding.py — 三层向量化兜底链：
GLM（EmbeddingPort，若配置且调用成功）
  -> BgeLocalEmbeddingClient（本地真实语义模型，见 model/repositories/embedding/
     bge_local_embedding.py；懒加载失败/推理异常则跳过）
  -> local_embed()（本模块，字符哈希，最后一层，恒不失败）

第一层不可用（没配置 embedding_model，或调用失败——网络问题、账户余额不足等，
见 project 备忘：GLM 账号没有 embedding 额度，/embeddings 恒 429）时退到第二层：
一个真正做语义理解的本地模型，不需要网络上的第三方 API。第二层本身也不可用
（缺依赖、模型下载失败等环境问题）才退到第三层——不需要网络/大模型，纯本地
计算的字符哈希词袋，兜底的兜底，恒不抛异常。

local_embed() 用字符 + 字符二元组的哈希词袋近似语义相似度：两段文字共享的字/
词越多，向量夹角越小。精度远不如真实 embedding 模型（分不出"意思相近但没有
共同字"的情况，比如"长剑"跟"兵刃"），但至少能分辨"完全不沾边" vs "明显相关"，
比彻底放弃匹配更有用。

维度（LOCAL_EMBEDDING_DIMS=128）刻意跟真实 embedding 模型的维度（bge-small-zh
是 512，GLM 的 embedding-3 是 2048…）区分开——真实向量和本地向量长度不同，
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


_bge_client = None


def _get_bge_client():
    global _bge_client
    if _bge_client is None:
        from model.repositories.embedding.bge_local_embedding import BgeLocalEmbeddingClient

        _bge_client = BgeLocalEmbeddingClient()
    return _bge_client


def embed_with_fallback(client: "EmbeddingPort | None", text: str) -> tuple[float, ...]:
    """所有需要向量化的地方统一走这个函数，不要直接调 client.embed()：三层依次
    尝试——client（一般是 GLM，为 None 或调用失败就跳过）-> 本地真实模型
    BgeLocalEmbeddingClient（加载/推理失败也跳过）-> local_embed()（字符哈希，
    恒不失败）。只要文字本身非空，永远能拿到一个可用于比较的向量，不会因为
    某一层向量服务不可用就让 predicate_text/物品匹配这类功能整个失效。"""
    if client is not None:
        try:
            vec = client.embed(text)
            if vec:
                return tuple(vec)
        except Exception as exc:
            _logger.warning("LLM 向量化失败，退回本地模型：%s", exc)
    try:
        vec = _get_bge_client().embed(text)
        if vec:
            return tuple(vec)
    except Exception as exc:
        _logger.warning("本地模型向量化失败，退回字符哈希兜底：%s", exc)
    return local_embed(text)


class FallbackEmbeddingClient:
    """EmbeddingPort：生产环境的统一入口，把三层兜底链包成一个永远不是 None 的
    客户端——controller/web_controller.py 用这个对象接线（不管 GLM 有没有配置/
    有没有 embedding 额度），predicate_text 判定、物品匹配、事件叙事重排等各处
    原有的 `embedding is None` 判断（README 里"向量模块关闭"的信号）不会再触发，
    因为向量功能现在总是"开着"的——GLM 有额度用 GLM，没有就用本地模型。

    单测继续显式传 `embedding=None` 或自己的 `_FakeEmbeddingPort`，不会构造这个
    类、也就不会意外触发真实模型加载——"关掉向量模块"这个测试场景仍然存在，只是
    不再是生产环境的常态。"""

    def __init__(self, primary: "EmbeddingPort | None") -> None:
        self._primary = primary

    def embed(self, text: str) -> list[float]:
        return list(embed_with_fallback(self._primary, text))
