#!/usr/bin/env bash
# Build the frontend SPA into backend/app/static (served by FastAPI).
set -euo pipefail
cd "$(dirname "$0")/../frontend"
npm install --no-audit --no-fund
npm run build
echo "[ok] Frontend built into backend/app/static"
