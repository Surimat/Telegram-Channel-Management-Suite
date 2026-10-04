#!/usr/bin/env bash
# Build the portable Windows distribution (PHASE 10).
#
# Produces a self-contained folder (and, by default, a versioned ZIP) that runs
# with no Python/Node/Docker installed, because it ships a relocatable CPython
# runtime and the already-built frontend.
#
# Usage:
#   scripts/build_portable.sh [output_dir] [--no-runtime] [--no-zip] [--no-frontend]
#
# Options:
#   --no-runtime   stage code only (no embedded Windows Python); the user adds a
#                  runtime later. Env SKIP_RUNTIME=1 is equivalent.
#   --no-zip       build the folder but do not create the ZIP archive.
#   --no-frontend  skip the npm build and reuse the already-built static SPA
#                  (offline / CI).
#
# Env:
#   VERSION        override the version used in the ZIP name (default: read from
#                  backend/app/__init__.py)
#   PYTHON         interpreter used to drive the cross-platform runtime builder
#
# Layout produced:
#   <output>/
#     app/         <- the application code (backend + built static frontend)
#     runtime/     <- embedded CPython (python.exe + site-packages)
#     data/ sessions/ backups/ logs/ exports/ models/
#     run.bat stop.bat README.txt .env.example
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT=""
PYTHON="${PYTHON:-python3}"
REQ_FILE="$ROOT/backend/requirements.txt"
LOCK_FILE="$ROOT/scripts/win-requirements.lock"

FETCH_RUNTIME=1
MAKE_ZIP=1
BUILD_FRONTEND=1
for arg in "$@"; do
  case "$arg" in
    --no-runtime) FETCH_RUNTIME=0 ;;
    --no-zip) MAKE_ZIP=0 ;;
    --no-frontend) BUILD_FRONTEND=0 ;;
    -*) echo "error: unknown option: $arg" >&2; exit 2 ;;
    *) OUT="$arg" ;;
  esac
done
[ "${SKIP_RUNTIME:-0}" = "1" ] && FETCH_RUNTIME=0

# Resolve the version (for the ZIP name) from the application package.
if [ -z "${VERSION:-}" ]; then
  VERSION="$("$PYTHON" - "$ROOT/backend/app/__init__.py" <<'PY' 2>/dev/null || true
import re, sys
text = open(sys.argv[1], encoding="utf-8").read()
m = re.search(r'__version__\s*=\s*"([^"]+)"', text)
print(m.group(1) if m else "0.0.0")
PY
)"
fi
VERSION="${VERSION:-0.0.0}"

OUT="${OUT:-$ROOT/dist/TelegramChannelManagementSuite}"
ZIP_NAME="Telegram-Channel-Management-Suite-Windows-Portable-${VERSION}.zip"
ZIP_PATH="$(dirname "$OUT")/$ZIP_NAME"

echo "==> Project root : $ROOT"
echo "==> Output dir   : $OUT"
echo "==> Version      : $VERSION"

# 1. Build the frontend into backend/app/static (served by FastAPI).
if [ "$BUILD_FRONTEND" = "1" ] && [ -d "$ROOT/frontend" ]; then
  echo "==> Building frontend"
  ( cd "$ROOT/frontend" && npm install --no-audit --no-fund && npm run build )
elif [ "$BUILD_FRONTEND" = "0" ]; then
  echo "==> Skipping frontend build (--no-frontend); using existing static SPA"
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
copy_item alembic.ini
copy_item migrations
copy_item pyproject.toml
copy_item requirements.txt
copy_item .env.example

# Remove anything that must never ship.
find "$OUT/app" -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true
find "$OUT/app" -type d -name ".pytest_cache" -prune -exec rm -rf {} + 2>/dev/null || true
find "$OUT/app" -name "*.pyc" -delete 2>/dev/null || true
# Never ship a stray .env, database, session or model file.
find "$OUT" -name ".env" -delete 2>/dev/null || true
find "$OUT" -name "*.session" -delete 2>/dev/null || true
find "$OUT" -name "*.db" -delete 2>/dev/null || true

# 4. Copy the portable launcher files to the distribution root.
cp "$ROOT/portable/run.bat" "$OUT/run.bat"
cp "$ROOT/portable/stop.bat" "$OUT/stop.bat"
cp "$ROOT/portable/README.txt" "$OUT/README.txt"
cp "$ROOT/.env.example" "$OUT/.env.example"

# 5. Stage the embedded Windows Python so run.bat needs no manual step (D-040).
#    Cross-platform: build_win_runtime.py downloads the embeddable CPython and
#    the win_amd64 wheels and extracts them flat (no compiler needed).
if [ "$FETCH_RUNTIME" = "1" ]; then
  echo "==> Staging embedded Windows Python into runtime/"
  "$PYTHON" "$ROOT/scripts/build_win_runtime.py" "$OUT/runtime" \
    --app-rel "../app" --lock "$LOCK_FILE" || {
      echo "warning: automatic runtime staging failed."
      echo "         Re-run scripts/build_win_runtime.py or finish on Windows (see README.txt)."
    }
else
  echo "==> Skipping runtime staging (--no-runtime)."
fi

# 6. Package the ZIP (portable-friendly: no extra wrapper directory).
if [ "$MAKE_ZIP" = "1" ]; then
  echo "==> Creating $ZIP_NAME"
  rm -f "$ZIP_PATH"
  if command -v zip >/dev/null 2>&1; then
    ( cd "$OUT" && zip -r -q -X "$ZIP_PATH" . )
  else
    "$PYTHON" - "$OUT" "$ZIP_PATH" <<'PY'
import os, sys, zipfile
root, out = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
    for dirpath, dirs, files in os.walk(root):
        rel = os.path.relpath(dirpath, root)
        # Preserve empty directories (e.g. data/, sessions/) in the archive.
        if rel != "." and not dirs and not files:
            zf.writestr(rel.replace(os.sep, "/") + "/", "")
        for name in files:
            full = os.path.join(dirpath, name)
            zf.write(full, os.path.relpath(full, root))
PY
  fi
  echo "==> ZIP: $ZIP_PATH"
  if command -v sha256sum >/dev/null 2>&1; then
    ( cd "$(dirname "$ZIP_PATH")" && sha256sum "$ZIP_NAME" | tee "$ZIP_NAME.sha256" )
  fi
fi

cat <<'NOTE'

==> Portable build complete.

If runtime/python.exe is present, double-click run.bat and the app starts with
no Python/Node/Docker installed.

If the runtime could not be staged (offline/restricted network), finish on
Windows:
  1. Download the "Windows embeddable package" for a matching Python version.
  2. Unzip it into <output>/runtime/ (python.exe, python3xx.dll, ...).
  3. Ensure <output>/runtime/python3xx._pth lists:  ../app  and  site-packages.
  4. Double-click run.bat.
NOTE
