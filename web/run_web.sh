#!/usr/bin/env bash
# Build the BigRedAlumni frontend and serve everything (API + SPA) from FastAPI on one port.
#
#   ./run_web.sh                 # production: build frontend, serve at :8000
#   DEV_AUTH_BYPASS=1 ./run_web.sh   # skip SMS; log in with any allowed phone + DEV_CODE (000000)
#
# For live-reload development run two processes instead:
#   (cd backend && DEV_AUTH_BYPASS=1 .venv/bin/python -m uvicorn main:app --reload --port 8000)
#   (cd frontend && npm run dev)     # http://localhost:5173 (proxies /api,/img to :8000)
set -euo pipefail
cd "$(dirname "$0")"

echo "==> Building frontend"
( cd frontend && npm install --no-audit --no-fund --silent && npm run build )

echo "==> Starting BigRedAlumni at http://localhost:${PORT:-8000}"
cd backend
exec .venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"
