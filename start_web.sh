#!/usr/bin/env bash
# start_web.sh -- launch the EventHorizon Web UI (controller/web_controller.py,
# FastAPI + a self-contained HTML/JS chat page, GAME_DESIGN §2 layout).
#
# eventhorizon/ is a src-style root (model/view/controller import as top-level
# packages), so we must run with that directory as the working directory --
# see conftest.py for the same convention used by the test suite.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST="${1:-127.0.0.1}"
PORT="${2:-8765}"

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
        echo "[start_web.sh] no working python/python3 found on PATH. Install Python 3.11+ and retry." >&2
        exit 1
    fi
fi

if ! "$PYTHON_BIN" -c "import fastapi, uvicorn" >/dev/null 2>&1; then
    echo "[start_web.sh] fastapi/uvicorn not installed for $PYTHON_BIN." >&2
    echo "                Install with: $PYTHON_BIN -m pip install fastapi uvicorn" >&2
    exit 1
fi

cd "$ROOT/eventhorizon"
echo "[start_web.sh] serving on http://$HOST:$PORT  (Ctrl+C to stop)"
exec "$PYTHON_BIN" -m controller.web_controller "$HOST" "$PORT"
