"""model/domain/cause.py — 因果模型（对应 README 1.9）。

把"仇杀、拜师、前世因果"收成统一数据，避免关系网、向量检索、流程图各写一套 if。
只存标签与过期，不存自由文本推理；一条行动可写多条 Link。
"""
from __future__ import annotations

from dataclasses import dataclass

from model.domain.time import GameTime


@dataclass(frozen=True, slots=True)
class CauseLink:
    """例：杀李四 → {玩家, 击杀, 李四亲友, 仇恨, 20年}。"""

    actor: str
    action: str
    target: str
    tag: str
    expires_at: GameTime | None = None

    def is_expired(self, now: GameTime) -> bool:
        return self.expires_at is not None and self.expires_at < now
