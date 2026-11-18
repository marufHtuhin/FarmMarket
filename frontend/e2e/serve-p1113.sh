#!/usr/bin/env bash
# Phase 11 (audit/p11-13): like e2e/serve.sh, but on port 8016 with its own
# scratch DB, so this agent's E2E runs never collide with the standard
# port-8000 setup (or with other audit agents). Used only with
# playwright.p1113.config.ts.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$ROOT/../backend"
DB="$ROOT/e2e/.e2e-p1113.db"

if [ ! -f "$ROOT/dist/index.html" ]; then
  echo "frontend/dist is missing — run 'npm run build' in frontend/ first." >&2
  exit 1
fi

if [ -n "${FARMMARKET_PYTHON:-}" ]; then
  PY="$FARMMARKET_PYTHON"
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
"$PY" seed_demo.py >/dev/null
exec "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port 8016
