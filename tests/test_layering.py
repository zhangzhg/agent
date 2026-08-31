"""tests/test_layering.py — 架构守卫测试（对应 README §9）。

这几条约束靠人工代码审查守不住，写成测试才有效：
  - model/domain/** 不 import model/repositories、view、sqlite3
  - play_turn.py / matching.py / chat_parser.py 的源码中不出现 LlmAuthorPort
  - controller/** 不 import pipeline / matching / arbiter
"""
import ast
import unittest
from pathlib import Path

_SRC_ROOT = Path(__file__).resolve().parent.parent / "eventhorizon"


def _imported_module_names(py_file: Path) -> set[str]:
    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


class DomainLayerIsolationTests(unittest.TestCase):
    FORBIDDEN_PREFIXES = ("model.repositories", "view", "controller", "sqlite3")

    def test_domain_does_not_import_repositories_view_or_sqlite3(self):
        violations = []
        for py_file in (_SRC_ROOT / "model" / "domain").rglob("*.py"):
            for name in _imported_module_names(py_file):
                if any(name == p or name.startswith(p + ".") for p in self.FORBIDDEN_PREFIXES):
                    violations.append(f"{py_file.relative_to(_SRC_ROOT)} imports {name!r}")
        self.assertEqual(violations, [], "\n".join(violations))


class PlayPathIsolationFromLlmAuthorTests(unittest.TestCase):
    """对局路径（play_turn / matching / chat_parser）禁止出现 LlmAuthorPort：
    该端口只注入录入用例（README 5.3 对局隔离）。"""

    FILES = (
        "model/services/play_turn.py",
        "model/services/matching.py",
        "model/services/chat_parser.py",
    )

    def test_llm_author_port_absent_from_play_path_sources(self):
        violations = []
        for rel_path in self.FILES:
            text = (_SRC_ROOT / rel_path).read_text(encoding="utf-8")
            if "LlmAuthorPort" in text:
                violations.append(rel_path)
        self.assertEqual(violations, [], f"LlmAuthorPort leaked into: {violations}")


class ControllerThinnessTests(unittest.TestCase):
    """controller/** 不直调 pipeline / matching / arbiter——那些全部封在
    bootstrap.py 的组合根里已经装配好的 PlayTurnService 中。"""

    FORBIDDEN_SUBSTRINGS = ("pipeline", "matching", "arbiter")

    def test_controller_files_do_not_import_pipeline_matching_or_arbiter(self):
        violations = []
        for py_file in (_SRC_ROOT / "controller").rglob("*.py"):
            for name in _imported_module_names(py_file):
                lowered = name.lower()
                if any(bad in lowered for bad in self.FORBIDDEN_SUBSTRINGS):
                    violations.append(f"{py_file.relative_to(_SRC_ROOT)} imports {name!r}")
        self.assertEqual(violations, [], "\n".join(violations))


if __name__ == "__main__":
    unittest.main()
