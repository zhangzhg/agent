"""content/onboarding.py — 开局叙述（GAME_DESIGN §1.1）。

不做强制教程；开局叙述本身暗示可做什么，靠系统消息里嵌自然语言提示。这是一段
纯文案，不是引擎逻辑——真正决定"提示还要不要继续出现"的是
PlayTurnService._soft_guidance_message，按 agent.turn_count 判断。
"""
from __future__ import annotations

OPENING_NARRATIVE = (
    "太乙历一百年，你生于苍梧城，是个六岁的孩童。\n"
    "街角传来阵阵饭香，酒楼里似乎有人在吆喝什么。\n"
    '（试着打字告诉我你想做什么，比如"去酒楼看看"）'
)
