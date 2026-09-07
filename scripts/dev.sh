#!/usr/bin/env bash
# Start the Decifra backend (FastAPI/uvicorn) and frontend (Vite) together with
# one command, for local development. Not a replacement for real packaging
# (see AGENTS.md's Phase 2 plan) -- just removes the "two terminals" step
# from the manual dev workflow documented in README.md.
#
# Usage: scripts/dev.sh [backend_port] [frontend_port]
# Defaults: backend 8000, frontend 5173 (Vite's own default).

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

BACKEND_PORT="${1:-8000}"
FRONTEND_PORT="${2:-5173}"
export VITE_API_BASE="http://localhost:${BACKEND_PORT}"

if [[ -x .venv/bin/python ]]; then
  PYTHON=.venv/bin/python
elif [[ -x .venv/Scripts/python.exe ]]; then
  PYTHON=.venv/Scripts/python.exe
else
  echo "Create this checkout's .venv and install .[dev] first." >&2
  exit 1
fi

PIDS=()
cleanup() {
  echo ""
  echo "Stopping Decifra..."
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT INT TERM

echo "Starting backend on http://localhost:${BACKEND_PORT} ..."
"$PYTHON" -m uvicorn text_as_data.app:app --port "$BACKEND_PORT" &
PIDS+=($!)

echo "Starting frontend on http://localhost:${FRONTEND_PORT} ..."
(cd frontend && npm run dev -- --port "$FRONTEND_PORT" --strictPort) &
PIDS+=($!)

echo ""
echo "Decifra is starting up:"
echo "  Backend:  http://localhost:${BACKEND_PORT}"
echo "  Frontend: http://localhost:${FRONTEND_PORT}"
echo ""
echo "Press Ctrl+C to stop both."

wait
