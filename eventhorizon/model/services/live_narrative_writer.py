"""model/services/live_narrative_writer.py — 事件命中但没有预先写好的文案变体时，
现场调 LLM 生成一句叙事。对应 README 对局第二段那张表格里的 LlmEventWriter："仍
默认抽库；可开 LlmEventWriter 临时补一条，建议事后再走 LlmEventAuthor 落库"。

跟 LlmEventAuthor（录入侧草稿生成器，README 5.3，明令不得出现在对局路径）不是
一回事：LlmEventWriter 本来就是设计给对局路径用的，README 表格把它跟"对局第二
段"放在一起——"对局隔离"那条约束针对的是 LlmAuthorPort（草稿生成，会往库里写
新事件定义、需要人工审核走发布流程），不针对这里。这里只做最低风险的事——给
一个已经存在、已经通过审核触发的事件补一句纯文本叙事，不产生新事件、不影响
谓词/结果池等任何机制字段。

调用方（PlayTurnService._ensure_variants）生成后会存回事件定义，下次同一事件
命中就不用再现场生成——不是每次触发都现编一句、也不是用完就扔。
"""
from __future__ import annotations

import logging
from typing import Protocol

_logger = logging.getLogger("eventhorizon.live_narrative_writer")

FALLBACK_TEMPLATE = "发生了一件与「{event_id}」有关的事。"


class LlmClient(Protocol):
    def complete(self, prompt: str) -> str: ...


def generate_live_variant_text(client: "LlmClient | None", event_id: str, tags: tuple[str, ...]) -> str:
    """client 为 None（没配置）或调用失败都返回一句朴素占位文案——这是对局热路径
    里少数几处可能打网络的地方之一，绝不能让它抛出去崩掉整个回合。"""
    fallback = FALLBACK_TEMPLATE.format(event_id=event_id)
    if client is None:
        return fallback
    prompt = (
        "你是一款文字修仙游戏的旁白。下面这个游戏事件被触发了，但还没有预先写好的"
        "叙事文案，请你现场写一句（第二人称，40-120字，古风白话文风格）。只输出这"
        "一句话，不要解释、不要加引号、不要任何多余文字。\n"
        f"事件标识：{event_id}\n"
        f"事件标签：{'、'.join(tags) if tags else '（无）'}\n"
    )
    try:
        text = client.complete(prompt).strip()
    except Exception:
        _logger.warning("LlmEventWriter 现场生成文案失败，退回占位文案：event_id=%s", event_id)
        return fallback
    return text or fallback
