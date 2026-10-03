#!/usr/bin/env bash
# Build the portable Windows distribution (PHASE 10).
#
# The result is a self-contained folder that runs with no Python/Node/Docker
# installed, because it ships a relocatable CPython runtime and the already
# built frontend. Run this on Windows (Git Bash / WSL with a Windows Python) or
# adapt PYTHON to a Windows interpreter path.
#
# Usage:
#   scripts/build_portable.sh [output_dir] [--no-runtime]
#
# Options:
#   --no-runtime   do not fetch an embedded Windows Python (stage code only;
#                  the user adds a runtime later). Env SKIP_RUNTIME=1 is equivalent.
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
REQ_FILE="$ROOT/backend/requirements.txt"

FETCH_RUNTIME=1
for arg in "$@"; do
  case "$arg" in
    --no-runtime) FETCH_RUNTIME=0 ;;
  esac
done
[ "${SKIP_RUNTIME:-0}" = "1" ] && FETCH_RUNTIME=0

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

# 5. Stage the embedded Windows Python so run.bat needs no manual step (D-040).
if [ "$FETCH_RUNTIME" = "1" ]; then
  echo "==> Staging embedded Windows Python into runtime/"
  bash "$ROOT/scripts/fetch_embedded_python.sh" "$OUT/runtime" \
    --requirements "$REQ_FILE" --app-rel "../app" || {
      echo "warning: automatic runtime staging failed; see the manual steps above."
    }
else
  echo "==> Skipping runtime fetch (--no-runtime)."
fi

# Also install deps into runtime/site-packages with the host interpreter as a
# best-effort fallback, so a manually-provided runtime already has them.
echo "==> Ensuring dependencies are present in runtime/site-packages"
"$PYTHON" -m pip install --no-cache-dir --target "$OUT/runtime/site-packages" \
  -r "$REQ_FILE" || echo "warning: could not pre-populate site-packages."

cat <<'NOTE'

==> Portable build staged at the output directory.

If an embedded Python was staged (runtime/python.exe present), double-click
run.bat and the app starts with no Python/Node/Docker installed.

If the runtime could not be fetched (offline/restricted network), finish on
Windows:
  1. Download the "Windows embeddable package" for a matching Python version.
  2. Unzip it into <output>/runtime/ (python.exe, python3xx.dll, ...).
  3. Ensure <output>/runtime/python3xx._pth lists:  ../app  and  site-packages.
  4. Double-click run.bat.

On Linux/macOS the staged tree also runs via:
  TCMS_ROOT=<output>/app python -m backend.app.main
NOTE
