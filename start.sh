#!/usr/bin/env bash
# start.sh -- launch the EventHorizon MVP CLI (controller/cli_controller.py).
#
# eventhorizon/ is a src-style root (model/view/controller import as top-level
# packages), so we must run with that directory as the working directory --
# see conftest.py for the same convention used by the test suite.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_ID="${1:-player}"

PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ]; then
    # Prefer "python", then "python3"; on Windows, `python3` on PATH is often the
    # Microsoft Store alias stub, which exits silently (no error message) if the
    # Store app isn't installed. Verify each candidate actually runs before using it.
    for candidate in python python3; do
        if command -v "$candidate" >/dev/null 2>&1 && "$candidate" --version >/dev/null 2>&1; then
            PYTHON_BIN="$candidate"
            break
        fi
    done
    if [ -z "$PYTHON_BIN" ]; then
        echo "[start.sh] no working python/python3 found on PATH. Install Python 3.11+ and retry." >&2
        exit 1
    fi
fi

cd "$ROOT/eventhorizon"
exec "$PYTHON_BIN" -m controller.cli_controller "$AGENT_ID"
