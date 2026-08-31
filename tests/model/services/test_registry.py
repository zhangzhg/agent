import logging
import unittest

from model.services.registry import EventRegistry, RegistryEntry


class RegistryTests(unittest.TestCase):
    def test_known_type_creates_via_factory(self):
        registry = EventRegistry()
        registry.register("Ping", RegistryEntry(factory=lambda d: {"ok": True, **d}, handler=None))
        result = registry.create({"type": "Ping", "n": 1})
        self.assertEqual(result["ok"], True)
        self.assertEqual(result["n"], 1)

    def test_unknown_type_returns_none_and_logs_warning(self):
        registry = EventRegistry()
        with self.assertLogs("eventhorizon.registry", level="WARNING"):
            result = registry.create({"type": "Nope"})
        self.assertIsNone(result)

    def test_migrate_fills_schema_version_default(self):
        registry = EventRegistry()
        seen = {}

        def factory(d):
            seen.update(d)
            return object()

        registry.register("X", RegistryEntry(factory=factory, handler=None, schema_version=3))
        registry.create({"type": "X"})
        self.assertEqual(seen.get("schema_version"), 3)


if __name__ == "__main__":
    unittest.main()
