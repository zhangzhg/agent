import unittest

from starlette.testclient import TestClient

from content.onboarding import OPENING_NARRATIVE
from controller.web_controller import create_app


def _client() -> TestClient:
    return TestClient(create_app(db_path=":memory:"))


class WebCharacterGateTests(unittest.TestCase):
    def test_create_enter_and_chat_require_verify_code(self):
        client = _client()
        created = client.post("/api/character", json={"agent_id": "张三"})
        self.assertEqual(created.status_code, 200)
        body = created.json()
        self.assertEqual(body["agent_id"], "张三")
        code = body["verify_code"]
        self.assertEqual(len(code), 6)

        again = client.post("/api/character", json={"agent_id": "张三"})
        self.assertEqual(again.status_code, 409)

        bad = client.post("/api/session", json={"agent_id": "张三", "verify_code": "XXXXXX"})
        self.assertEqual(bad.status_code, 401)

        entered = client.post("/api/session", json={"agent_id": "张三", "verify_code": code})
        self.assertEqual(entered.status_code, 200)
        self.assertIn(OPENING_NARRATIVE, entered.json()["narrative"])
        self.assertFalse(entered.json()["event_expired"])

        denied = client.post("/api/chat", json={"agent_id": "张三", "verify_code": "XXXXXX", "text": "看一看"})
        self.assertEqual(denied.status_code, 401)

        ok = client.post("/api/chat", json={"agent_id": "张三", "verify_code": code, "text": "看一看"})
        self.assertEqual(ok.status_code, 200)
        self.assertTrue(ok.json()["narrative"])

    def test_invalid_agent_id_is_400(self):
        client = _client()
        resp = client.post("/api/character", json={"agent_id": "x"})
        self.assertEqual(resp.status_code, 400)

    def test_chat_page_starts_with_create_or_enter_menu(self):
        client = _client()
        page = client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("1) 建立人物", page.text)
        self.assertIn("2) 进入游戏", page.text)
        menu = 'const MENU = "请选择：\\n1) 建立人物\\n2) 进入游戏"'
        self.assertIn(menu, page.text)
        self.assertNotIn("id=\"gate\"", page.text)

    def test_get_session_is_gone(self):
        client = _client()
        resp = client.get("/api/session")
        self.assertEqual(resp.status_code, 405)


if __name__ == "__main__":
    unittest.main()
