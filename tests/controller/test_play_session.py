import unittest

from controller.play_session import open_play_session
from model.services.local_embedding import FallbackEmbeddingClient
from model.services.world_query_assistant import WorldQueryAssistant


class OpenPlaySessionTests(unittest.TestCase):
    def test_cli_and_web_share_the_same_play_stack(self):
        session = open_play_session(db_path=":memory:")
        self.assertTrue(session.app.world.locations)
        self.assertIsInstance(session.embedding, FallbackEmbeddingClient)
        self.assertIs(session.app.play_turn.embedding, session.embedding)
        self.assertIs(session.controller._characters, session.app.character_service)
        if session.llm_client is None:
            self.assertIsNone(session.controller._world_query)
            self.assertIsNone(session.app.play_turn.narrative_writer)
        else:
            self.assertIsInstance(session.controller._world_query, WorldQueryAssistant)
            self.assertIs(session.app.play_turn.narrative_writer, session.llm_client)


if __name__ == "__main__":
    unittest.main()
