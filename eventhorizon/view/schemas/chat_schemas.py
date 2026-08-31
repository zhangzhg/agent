"""view/schemas/chat_schemas.py — 聊天接口的请求/响应 DTO（对应 README §6 / §10）。

MVP 不引入 pydantic（保持 model 包框架无关）；V1+ 接 FastAPI 时，可在 controller
层把这里的 dataclass 与 Pydantic 模型互转，不改 model 包本身。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ChatRequest:
    agent_id: str
    text: str


@dataclass
class ChatResponse:
    narrative: str
    state_diff_lines: list[str] = field(default_factory=list)
    agent_state: str = ""
    parse_error: str | None = None
    reject_reason: str | None = None
