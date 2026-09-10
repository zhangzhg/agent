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

    def complete_with_tools(self, messages: list[dict], tools: list[dict]) -> dict:
        """跟 complete() 是同一个 /chat/completions 端点，多带一个 tools 参数——
        GLM 的 OpenAI 兼容层支持标准 tools/tool_calls 协议。返回原始 message 对象
        而不是直接取 content：模型要调工具时 content 可能是 None，tool_calls 才是
        有效载荷，判断走哪条分支、本地执行、把结果拼回 messages 再问一轮，都是
        调用方（model/services/llm_tool_loop.py）的事，这里只管收发一次请求。"""
        response = httpx.post(
            f"{self._config.base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {self._config.api_key}"},
            json={
                "model": self._config.model,
                "messages": messages,
                "tools": tools,
                "temperature": 0.9,
            },
            timeout=self._config.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]

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
