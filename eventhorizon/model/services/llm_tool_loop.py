"""model/services/llm_tool_loop.py — 标准 OpenAI 风格的工具调用循环：给一个
支持 `complete_with_tools(messages, tools) -> message` 的客户端、一批工具定义、
和工具名到本地实现的映射，跑到模型给出最终文本答案为止。

目前唯一的调用方是 model/services/live_content_author.py（地点创作时查真实
地点列表，见 README §1.12 的 LiveContentAuthor 例外说明）——工具本身不受
"对局隔离"约束（只读查询，不写库），跟 EmbeddingPort 是同一类"对局路径本来就
该能用"的能力。
"""
from __future__ import annotations

import json
import logging
from typing import Callable, Protocol

_logger = logging.getLogger("eventhorizon.llm_tool_loop")


class LlmToolClient(Protocol):
    def complete_with_tools(self, messages: list[dict], tools: list[dict]) -> dict: ...


def run_tool_loop(
    client: LlmToolClient,
    messages: list[dict],
    tools: list[dict],
    tool_impls: dict[str, Callable[..., dict]],
    max_rounds: int = 3,
) -> str | None:
    """messages 是初始对话（一般就是一条 role=user 的 prompt），tools 是 OpenAI
    风格的工具定义数组，tool_impls 是工具名 -> 本地函数（接收解析好的参数 dict，
    返回一个可 JSON 序列化的结果）。max_rounds 是这一次请求内部的安全阀（防止
    模型反复要工具、永远给不出最终答案），不是玩家追问轮次——那个是
    play_turn.py 里 PendingClarification.attempts 的事，两者互不影响。

    模型给出 content（哪怕同时也给了 tool_calls，OpenAI 协议允许但少见）就当
    最终答案返回；工具调用异常/未知工具名不让整个循环崩掉，塞一条错误结果让
    模型自己决定怎么应对（通常是换个说法回答或者放弃）。跑满 max_rounds 还没有
    最终答案，返回 None——调用方按"调用失败"处理，不是"模型说了空字符串"。"""
    conversation = list(messages)
    for _ in range(max_rounds):
        try:
            message = client.complete_with_tools(conversation, tools)
        except Exception as exc:
            _logger.warning("工具调用循环里 LLM 请求失败：%s", exc)
            return None
        tool_calls = message.get("tool_calls")
        if not tool_calls:
            return message.get("content")
        conversation.append(message)
        for call in tool_calls:
            name = call.get("function", {}).get("name")
            raw_args = call.get("function", {}).get("arguments") or "{}"
            try:
                args = json.loads(raw_args)
            except json.JSONDecodeError:
                args = {}
            impl = tool_impls.get(name)
            if impl is None:
                result = {"error": f"未知工具：{name}"}
            else:
                try:
                    result = impl(**args)
                except Exception as exc:
                    _logger.warning("工具 %s 执行失败：%s", name, exc)
                    result = {"error": str(exc)}
            conversation.append({
                "role": "tool", "tool_call_id": call.get("id"),
                "content": json.dumps(result, ensure_ascii=False),
            })
    _logger.warning("工具调用循环超过 %d 轮仍未得到最终答案", max_rounds)
    return None
