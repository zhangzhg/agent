import sqlite3
import unittest

from model.domain.agent import AgentEventHistory, PendingScenario
from model.domain.items import Inventory
from model.domain.states import DeadState, EncounterPendingState, IdleState
from model.repositories.character_repository import (
    CharacterExistsError,
    CharacterRecord,
    InMemoryCharacterRepository,
    SqliteCharacterRepository,
)
from model.services.character_service import (
    EVENT_SNAPSHOT_TTL_SECONDS,
    CharacterAuthError,
    CharacterService,
    InvalidAgentIdError,
)
from tests.helpers import make_agent, make_time


class _AgentStore:
    def __init__(self) -> None:
        self._agents: dict[str, object] = {}

    def load(self, agent_id: str):
        if agent_id not in self._agents:
            raise LookupError(agent_id)
        return self._agents[agent_id]

    def save(self, agent) -> None:
        self._agents[agent.agent_id] = agent


class CharacterServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = 1_000.0
        self.agents = _AgentStore()
        self.characters = InMemoryCharacterRepository()
        self.svc = CharacterService(
            self.characters,
            self.agents,
            create_agent=self._spawn,
            now=lambda: self.now,
        )

    def _spawn(self, agent_id: str):
        agent = make_agent(agent_id=agent_id, money=10, cultivation=0.0, inventory=Inventory())
        self.agents.save(agent)
        return agent

    def test_create_and_enter_keeps_pending_within_ttl(self):
        created = self.svc.create("张三")
        agent = self.agents.load("张三")
        agent.pending_encounter_id = "wine"
        agent.state = EncounterPendingState()
        agent.money = 88
        agent.inventory.add("pill", 2)
        self.svc.save_player(agent)

        entered = self.svc.enter("张三", created.verify_code)
        self.assertFalse(entered.event_expired)
        self.assertEqual(entered.agent.pending_encounter_id, "wine")
        self.assertEqual(entered.agent.money, 88)
        self.assertTrue(entered.agent.inventory.has("pill", 2))

    def test_expiry_clears_events_but_keeps_attrs_and_inventory(self):
        created = self.svc.create("张三")
        agent = self.agents.load("张三")
        agent.pending_encounter_id = "wine"
        agent.pending_scenario = PendingScenario("s", "n", "h")
        agent.pending_retreat_prompt = True
        agent.scene_focus = "金龙鱼"
        agent.state = EncounterPendingState()
        agent.event_history = AgentEventHistory(triggers={"eat": [make_time()]})
        agent.money = 99
        agent.cultivation = 12.5
        agent.inventory.add("lingshi", 3)
        self.svc.save_player(agent)

        self.now += EVENT_SNAPSHOT_TTL_SECONDS + 1
        entered = self.svc.enter("张三", created.verify_code)

        self.assertTrue(entered.event_expired)
        self.assertIsNone(entered.agent.pending_encounter_id)
        self.assertIsNone(entered.agent.pending_scenario)
        self.assertFalse(entered.agent.pending_retreat_prompt)
        self.assertIsNone(entered.agent.scene_focus)
        self.assertEqual(entered.agent.event_history.triggers, {})
        self.assertIsInstance(entered.agent.state, IdleState)
        self.assertEqual(entered.agent.money, 99)
        self.assertEqual(entered.agent.cultivation, 12.5)
        self.assertTrue(entered.agent.inventory.has("lingshi", 3))

    def test_expiry_does_not_revive_the_dead(self):
        created = self.svc.create("张三")
        agent = self.agents.load("张三")
        agent.state = DeadState()
        agent.pending_encounter_id = "wine"
        self.svc.save_player(agent)
        self.now += EVENT_SNAPSHOT_TTL_SECONDS + 1

        entered = self.svc.enter("张三", created.verify_code)
        self.assertTrue(entered.event_expired)
        self.assertIsInstance(entered.agent.state, DeadState)
        self.assertIsNone(entered.agent.pending_encounter_id)

    def test_duplicate_or_npc_id_is_rejected(self):
        self.svc.create("张三")
        with self.assertRaises(CharacterExistsError):
            self.svc.create("张三")
        self.agents.save(make_agent(agent_id="王麻子", is_npc=True))
        with self.assertRaises(CharacterExistsError):
            self.svc.create("王麻子")

    def test_auth_rejects_bad_code_and_short_id(self):
        created = self.svc.create("张三")
        with self.assertRaises(CharacterAuthError):
            self.svc.authenticate("张三", "WRONG1")
        self.svc.authenticate("张三", created.verify_code.lower())
        with self.assertRaises(InvalidAgentIdError):
            self.svc.create("x")


class SqliteCharacterRepositoryTests(unittest.TestCase):
    def test_round_trip_and_touch(self):
        repo = SqliteCharacterRepository(sqlite3.connect(":memory:"))
        record = CharacterRecord("甲", "hash", 1.0, 2.0)
        repo.create(record)
        self.assertEqual(repo.get("甲"), record)
        repo.touch_event_saved_at("甲", 9.0)
        self.assertEqual(repo.get("甲").event_saved_at, 9.0)
        with self.assertRaises(CharacterExistsError):
            repo.create(record)


if __name__ == "__main__":
    unittest.main()
