#!/usr/bin/env bash
# Start the FarmMarket backend (serving the built React SPA from
# frontend/dist) on a scratch SQLite DB for Playwright E2E tests.
# The frontend must be built first: `npm run build` from frontend/.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$ROOT/../backend"
DB="$ROOT/e2e/.e2e.db"
# Port override (default 8000) so parallel audit runs don't collide.
E2E_PORT="${E2E_PORT:-8000}"

if [ ! -f "$ROOT/dist/index.html" ]; then
  echo "frontend/dist is missing — run 'npm run build' in frontend/ first." >&2
  exit 1
fi

# Resolve a Python with the backend dependencies installed. Override with
# FARMMARKET_PYTHON=/path/to/python if none of these fit your machine.
if [ -n "${FARMMARKET_PYTHON:-}" ]; then
  PY="$FARMMARKET_PYTHON"
elif [ -x "$BACKEND/venv/bin/python" ]; then
  PY="$BACKEND/venv/bin/python"
elif [ -x "$BACKEND/venv/Scripts/python.exe" ]; then
  PY="$BACKEND/venv/Scripts/python.exe"
elif [ -x "$ROOT/../.venv/bin/python" ]; then
  PY="$ROOT/../.venv/bin/python"
elif [ -x "$ROOT/../../.venv/bin/python" ]; then
  PY="$ROOT/../../.venv/bin/python"
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  PY=python3
fi

rm -f "$DB"
export DATABASE_URL="sqlite:///$DB"
export SECRET_KEY="e2e-test-secret-key-do-not-use-in-production"
cd "$BACKEND"
# Seed demo users (farmer/buyer/transporter/admin) + demo data.
"$PY" seed_demo.py >/dev/null
exec "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$E2E_PORT"
