"""model/repositories/llm/openai_compatible_client.py — LlmClient/EmbeddingPort
协议的一个具体实现，对接任意"OpenAI 兼容 /chat/completions + /embeddings"接口
（官方 OpenAI、各类兼容网关，也包括不少本地部署的模型服务）。不绑定某一家厂商
SDK，走 llm_event_author.py / llm_location_author.py 里各自定义的 LlmClient
Protocol（结构一致：只要有一个 complete(prompt) -> str 方法）和
model/services/ports.py 的 EmbeddingPort（embed(text) -> list[float]），连接
信息从 llm_config.py 读，不在这里硬编码。
"""
from __future__ import annotations

import httpx

from model.repositories.llm.llm_config import LlmConnectionConfig


class OpenAiCompatibleClient:
    def __init__(self, config: LlmConnectionConfig) -> None:
        self._config = config

    def complete(self, prompt: str) -> str:
        response = httpx.post(
            f"{self._config.base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {self._config.api_key}"},
            json={
                "model": self._config.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.9,
            },
            timeout=self._config.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

    def embed(self, text: str) -> list[float]:
        """EmbeddingPort 的实现——只有事件"触发条件"改用向量相似度判定这一个用途
        在用（model/services/matching.py 的 predicate_text 分支），用的是
        embedding_model（跟 chat completions 的 model 是两个不同的模型）。"""
        response = httpx.post(
            f"{self._config.base_url.rstrip('/')}/embeddings",
            headers={"Authorization": f"Bearer {self._config.api_key}"},
            json={"model": self._config.embedding_model, "input": text},
            timeout=self._config.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        return list(data["data"][0]["embedding"])
