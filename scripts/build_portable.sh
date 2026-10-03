#!/usr/bin/env bash
# Build the portable Windows distribution (PHASE 10).
#
# The result is a self-contained folder that runs with no Python/Node/Docker
# installed, because it ships a relocatable CPython runtime and the already
# built frontend. Run this on Windows (Git Bash / WSL with a Windows Python) or
# adapt PYTHON to a Windows interpreter path.
#
# Usage:
#   scripts/build_portable.sh [output_dir]
#
# Layout produced:
#   <output>/
#     app/         <- the application code (backend + built static frontend)
#     runtime/     <- embedded CPython (python.exe + site-packages)
#     data/ sessions/ backups/ logs/ exports/ models/
#     run.bat stop.bat README.txt .env.example
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$ROOT/dist/TelegramChannelManagementSuite}"
PYTHON="${PYTHON:-python}"

echo "==> Project root : $ROOT"
echo "==> Output dir   : $OUT"

# 1. Build the frontend into backend/app/static (served by FastAPI).
if [ -d "$ROOT/frontend" ]; then
  echo "==> Building frontend"
  ( cd "$ROOT/frontend" && npm install --no-audit --no-fund && npm run build )
fi

# 2. Fresh output tree.
echo "==> Preparing output tree"
rm -rf "$OUT"
mkdir -p "$OUT/app" "$OUT/runtime" "$OUT/data" "$OUT/sessions" \
         "$OUT/backups" "$OUT/logs" "$OUT/exports" "$OUT/models"

# 3. Copy application code (no VCS, caches, data or secrets).
echo "==> Copying application code"
copy_item() {
  local name="$1"
  if [ -e "$ROOT/$name" ]; then
    cp -R "$ROOT/$name" "$OUT/app/$name"
  fi
}
copy_item backend
copy_item frontend/dist 2>/dev/null || true
copy_item pyproject.toml
copy_item requirements.txt
copy_item .env.example

# Remove anything that must never ship.
find "$OUT/app" -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true
find "$OUT/app" -type d -name ".pytest_cache" -prune -exec rm -rf {} + 2>/dev/null || true
find "$OUT/app" -name "*.pyc" -delete 2>/dev/null || true

# 4. Copy the portable launcher files to the distribution root.
cp "$ROOT/portable/run.bat" "$OUT/run.bat"
cp "$ROOT/portable/stop.bat" "$OUT/stop.bat"
cp "$ROOT/portable/README.txt" "$OUT/README.txt"
cp "$ROOT/portable/.env.example" "$OUT/.env.example" 2>/dev/null || \
  cp "$ROOT/.env.example" "$OUT/.env.example" 2>/dev/null || true

# 5. Install the Python dependencies into the embedded runtime.
#    (Real embedding uses the python.org "embeddable" zip on Windows; here we
#    vendor the current interpreter's site-packages as a portable base.)
echo "==> Installing Python dependencies into runtime/"
"$PYTHON" -m pip install --no-cache-dir --target "$OUT/runtime/site-packages" \
  -r "$ROOT/requirements.txt"

cat <<'NOTE'

==> Portable build staged at the output directory.

To finish on Windows, place a relocatable CPython next to the app:
  1. Download the "Windows embeddable package" for the same Python version.
  2. Unzip it into <output>/runtime/ (python.exe, python3xx.dll, ...).
  3. Add a runtime/python3xx._pth line:  ../app
     and:  ../runtime/site-packages
  4. Double-click run.bat.

On Linux/macOS the staged tree also runs via:
  TCMS_ROOT=<output>/app python -m backend.app.main
NOTE
