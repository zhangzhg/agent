import json
import os
import tempfile
import unittest
from pathlib import Path

from model.repositories.llm.llm_config import LlmConnectionConfig, load_llm_config


class LoadLlmConfigTests(unittest.TestCase):
    def _write_config(self, data: dict) -> Path:
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        Path(path).write_text(json.dumps(data), encoding="utf-8")
        self.addCleanup(lambda: Path(path).unlink(missing_ok=True))
        return Path(path)

    def test_missing_file_returns_unconfigured(self):
        cfg = load_llm_config(Path("does_not_exist_anywhere.json"))
        self.assertEqual(cfg, LlmConnectionConfig())
        self.assertFalse(cfg.configured)

    def test_literal_api_key_used_directly(self):
        path = self._write_config({
            "provider": "openai-compatible", "base_url": "https://api.example.com/v1",
            "model": "gpt-test", "api_key": "sk-literal",
        })
        cfg = load_llm_config(path)
        self.assertEqual(cfg.api_key, "sk-literal")
        self.assertTrue(cfg.configured)

    def test_api_key_env_used_when_literal_key_blank(self):
        path = self._write_config({
            "base_url": "https://api.example.com/v1", "model": "gpt-test",
            "api_key": "", "api_key_env": "EVENTHORIZON_TEST_KEY_VAR",
        })
        os.environ["EVENTHORIZON_TEST_KEY_VAR"] = "sk-from-env"
        self.addCleanup(lambda: os.environ.pop("EVENTHORIZON_TEST_KEY_VAR", None))
        cfg = load_llm_config(path)
        self.assertEqual(cfg.api_key, "sk-from-env")
        self.assertTrue(cfg.configured)

    def test_no_key_anywhere_is_unconfigured(self):
        path = self._write_config({"base_url": "https://api.example.com/v1", "model": "gpt-test"})
        cfg = load_llm_config(path)
        self.assertEqual(cfg.api_key, "")
        self.assertFalse(cfg.configured)

    def test_malformed_json_returns_unconfigured_not_raise(self):
        fd, raw_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        Path(raw_path).write_text("{not valid json", encoding="utf-8")
        self.addCleanup(lambda: Path(raw_path).unlink(missing_ok=True))
        cfg = load_llm_config(Path(raw_path))
        self.assertFalse(cfg.configured)


if __name__ == "__main__":
    unittest.main()
