"""model/repositories/embedding/bge_local_embedding.py — EmbeddingPort 的本地真实
模型实现：GLM 没有 embedding 额度时（见 project 备忘：/embeddings 恒 429）的第二层
兜底（第一层是 GLM，第三层是 model/services/local_embedding.py 的字符哈希兜底），
不需要网络上的第三方 API，纯本地推理。

用 sentence-transformers 加载 BAAI/bge-small-zh-v1.5——一个真正做语义理解的中文
向量模型，跟字符哈希兜底完全不是一个量级：分得出"意思相近但没有共同字"的情况。
首次调用会从 HuggingFace Hub 下载模型权重到本地缓存（~100MB，之后离线可用）。

模型只在第一次真正调用 embed() 时才加载（懒加载的模块级单例）——纯 CLI 跑局、
没用到任何向量功能的路径不需要为用不到的模型付加载成本。
"""
from __future__ import annotations

import logging
import threading

_logger = logging.getLogger("eventhorizon.bge_local_embedding")

MODEL_NAME = "BAAI/bge-small-zh-v1.5"

_model = None
_model_lock = threading.Lock()


def _get_model():
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                from sentence_transformers import SentenceTransformer

                _logger.info("加载本地向量模型 %s（首次调用，可能需要下载权重）", MODEL_NAME)
                _model = SentenceTransformer(MODEL_NAME)
    return _model


class BgeLocalEmbeddingClient:
    """EmbeddingPort 的实现：本地推理，不依赖网络上的第三方 API。加载/推理失败
    （缺依赖、模型下载失败、内存不足等）都让异常自然抛出——调用方统一走
    model/services/local_embedding.py 的 embed_with_fallback() 兜底到下一层，
    这里不用再自己 try/except 一遍。"""

    def embed(self, text: str) -> list[float]:
        model = _get_model()
        return model.encode(text, normalize_embeddings=True).tolist()
