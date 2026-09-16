"""model/services/character_service.py — 建角、验证码校验、事件快照三日过期。

物品/属性在 Agent 存档里永久保存。事件相关挂起态与 event_history 是「任务事件
快照」：墙钟超过三天再进入游戏时清掉，修为、行囊、境界不动。
"""
from __future__ import annotations

import hashlib
import random
import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from model.domain.agent import AgentEventHistory
from model.domain.states import IdleState
from model.repositories.character_repository import CharacterExistsError, CharacterRecord

if TYPE_CHECKING:
    from model.domain.agent import Agent
    from model.services.ports import AgentRepository, CharacterRepository

EVENT_SNAPSHOT_TTL_SECONDS = 3 * 24 * 60 * 60
EVENT_EXPIRED_NARRATIVE = (
    "三日已过，先前未了的机缘已随风散去。你的修为与行囊仍在。"
)
_VERIFY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_AGENT_ID_RE = re.compile(r"^[\w\u4e00-\u9fff\-]{2,16}$")


class CharacterAuthError(ValueError):
    pass


class InvalidAgentIdError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CreatedCharacter:
    agent_id: str
    verify_code: str


@dataclass(frozen=True, slots=True)
class EnterResult:
    agent: "Agent"
    event_expired: bool


def normalize_agent_id(raw: str) -> str:
    agent_id = (raw or "").strip()
    if not _AGENT_ID_RE.fullmatch(agent_id):
        raise InvalidAgentIdError("人物 id 须为 2～16 个字，限中文、字母、数字、下划线或短横线。")
    return agent_id


def hash_verify_code(agent_id: str, code: str) -> str:
    return hashlib.sha256(f"{agent_id}\0{code.strip().upper()}".encode("utf-8")).hexdigest()


def generate_verify_code(rng: random.Random) -> str:
    return "".join(rng.choice(_VERIFY_ALPHABET) for _ in range(6))


def clear_event_state(agent: "Agent") -> None:
    """清掉任务/奇遇挂起与事件历史，不动物品和属性。死亡仍是死亡。"""
    agent.event_history = AgentEventHistory()
    agent.pending_encounter_id = None
    agent.pending_scenario = None
    agent.pending_clarification = None
    agent.pending_live_result = None
    agent.pending_retreat_prompt = False
    agent.scene_focus = None
    if agent.state.name != "dead":
        agent.state = IdleState()


class CharacterService:
    def __init__(
        self,
        characters: "CharacterRepository",
        agents: "AgentRepository",
        create_agent: Callable[[str], "Agent"],
        rng: random.Random | None = None,
        now: Callable[[], float] | None = None,
    ) -> None:
        self._characters = characters
        self._agents = agents
        self._create_agent = create_agent
        self._rng = rng or random.Random()
        self._now = now or time.time

    def create(self, raw_agent_id: str) -> CreatedCharacter:
        agent_id = normalize_agent_id(raw_agent_id)
        if self._characters.get(agent_id) is not None:
            raise CharacterExistsError(agent_id)
        try:
            self._agents.load(agent_id)
        except LookupError:
            pass
        else:
            raise CharacterExistsError(agent_id)
        verify_code = generate_verify_code(self._rng)
        now = self._now()
        self._characters.create(
            CharacterRecord(
                agent_id=agent_id,
                verify_code_hash=hash_verify_code(agent_id, verify_code),
                created_at=now,
                event_saved_at=now,
            )
        )
        self._create_agent(agent_id)
        return CreatedCharacter(agent_id=agent_id, verify_code=verify_code)

    def authenticate(self, raw_agent_id: str, verify_code: str) -> CharacterRecord:
        agent_id = normalize_agent_id(raw_agent_id)
        record = self._characters.get(agent_id)
        if record is None or record.verify_code_hash != hash_verify_code(agent_id, verify_code):
            raise CharacterAuthError("人物 id 或验证码不对。")
        return record

    def enter(self, raw_agent_id: str, verify_code: str) -> EnterResult:
        record = self.authenticate(raw_agent_id, verify_code)
        agent = self._agents.load(record.agent_id)
        expired = self._now() - record.event_saved_at > EVENT_SNAPSHOT_TTL_SECONDS
        if expired:
            clear_event_state(agent)
            self.save_player(agent)
        return EnterResult(agent=agent, event_expired=expired)

    def save_player(self, agent: "Agent") -> None:
        """对局回合结束后：永久属性进 Agent 存档，并刷新事件快照墙钟。"""
        self._agents.save(agent)
        if self._characters.get(agent.agent_id) is not None:
            self._characters.touch_event_saved_at(agent.agent_id, self._now())
