"""model/services/arbiter.py — EventArbiter（对应 README 1.7）。

ENQUEUE 的语义是明确的：不执行结果池，只把 event_id 写进
agent.pending_encounter_id（经 diff），等主行为结束后由玩家下一句决定接不接。
PlayTurnService 必须显式处理这个分支——把 ENQUEUE 当 EXECUTE 放过去，就等于奇遇
抢占了主行为。同一时刻只允许一个挂起项：已有 pending_encounter_id 时新的
ENQUEUE 直接丢弃，不排队堆积。
"""
from __future__ import annotations

from enum import Enum, auto

from model.domain.events import TriggerSource


class ArbitrationDecision(Enum):
    EXECUTE = auto()
    ENQUEUE = auto()
    DISCARD = auto()


SOURCE_RANK = {  # 数字小 = 强，对应 README 1.7 的四级
    TriggerSource.FORCE: 0,
    TriggerSource.PLAYER: 1,
    TriggerSource.SCHEDULE: 2,
    TriggerSource.ENCOUNTER: 3,
    TriggerSource.CHAIN: 1,  # 默认随触发它的那条，由调用方显式覆盖
}


class EventArbiter:
    def decide(
        self,
        agent_current_state: str,
        incoming_source: TriggerSource,
        incoming_priority: int,  # GameEventDef.priority，录入时配置的默认等级
        current_priority: int | None,  # 正在进行的主行为等级；idle 时为 None
    ) -> ArbitrationDecision:
        """README 1.7：读事件元数据的默认优先级，投递时的 TriggerSource 可覆盖。
        实际等级 = (SOURCE_RANK[source], incoming_priority)，先比来源再比事件配置。"""
        if incoming_source is TriggerSource.FORCE:
            return ArbitrationDecision.EXECUTE  # 强制级立即中断
        if agent_current_state == "dead":
            return ArbitrationDecision.DISCARD
        if agent_current_state == "closed_door":
            return ArbitrationDecision.DISCARD  # 非 force 一律不打扰闭关
        if agent_current_state in ("encounter_pending", "scenario_pending"):
            # 挂起等回话期间，只认玩家；日程/奇遇丢弃，避免把玩家的选择窗口冲掉
            return (
                ArbitrationDecision.EXECUTE
                if incoming_source is TriggerSource.PLAYER
                else ArbitrationDecision.DISCARD
            )
        if agent_current_state == "acting":
            if incoming_source is TriggerSource.PLAYER:
                return ArbitrationDecision.EXECUTE  # 玩家抢占日程
            if incoming_source is TriggerSource.ENCOUNTER:
                return ArbitrationDecision.ENQUEUE  # 奇遇不抢主行为，挂为可选分支
            if current_priority is not None and incoming_priority < current_priority:
                return ArbitrationDecision.EXECUTE  # 同来源下按事件配置的等级比
            return ArbitrationDecision.DISCARD
        return ArbitrationDecision.EXECUTE
