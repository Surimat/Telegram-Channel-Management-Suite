#!/usr/bin/env bash
# Development runner: starts the FastAPI app (backend + built SPA).
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "[i] .env not found; creating from .env.example"
  cp .env.example .env
fi

if [ -d .venv ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

exec python -m backend.app.main
