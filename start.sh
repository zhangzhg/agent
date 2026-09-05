#!/usr/bin/env bash
# start.sh -- launch the EventHorizon MVP: either the terminal CLI
# (controller/cli_controller.py) or the web UI (controller/web_controller.py,
# FastAPI + a self-contained HTML/JS chat page, GAME_DESIGN §2 layout).
#
# eventhorizon/ is a src-style root (model/view/controller import as top-level
# packages), so we must run with that directory as the working directory --
# see conftest.py for the same convention used by the test suite.
#
# Usage:
#   start.sh                     CLI, agent_id=player
#   start.sh <agent_id>          CLI, custom agent_id
#   start.sh web [host] [port]   Web UI, default 127.0.0.1:8765
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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

if [ "${1:-}" = "web" ]; then
    shift
    HOST="${1:-127.0.0.1}"
    PORT="${2:-8765}"
    # fastapi/uvicorn are regular project dependencies (see pyproject.toml)
    # -- Web is not a separate optional add-on, so this is "project not set
    # up yet", not "web extra missing".
    if ! "$PYTHON_BIN" -c "import fastapi, uvicorn" >/dev/null 2>&1; then
        echo "[start.sh] project dependencies not installed for $PYTHON_BIN." >&2
        echo "            Install with: $PYTHON_BIN -m pip install -r \"$ROOT/requirements.txt\"" >&2
        exit 1
    fi
    echo "[start.sh] serving on http://$HOST:$PORT  (Ctrl+C to stop)"
    exec "$PYTHON_BIN" -m controller.web_controller "$HOST" "$PORT"
fi

AGENT_ID="${1:-player}"
exec "$PYTHON_BIN" -m controller.cli_controller "$AGENT_ID"
