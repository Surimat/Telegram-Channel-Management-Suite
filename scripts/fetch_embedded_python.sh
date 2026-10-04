#!/usr/bin/env bash
# Stage a relocatable Windows CPython ("embeddable package") into a runtime
# directory so the portable build runs with no Python installed (D-040).
#
# Usage:
#   scripts/fetch_embedded_python.sh <runtime_dir> [options]
#
# Options:
#   --version X.Y.Z      Python version to fetch (default: host version, else 3.12.7)
#   --arch ARCH          amd64 (default) | win32 | arm64
#   --requirements FILE  install these deps into <runtime_dir>/site-packages
#   --app-rel PATH       relative app path added to the ._pth (default: ../app)
#   --no-deps            only fetch/extract CPython; do NOT install dependencies
#                        (the caller stages wheels itself; used by build_portable.sh)
#   --dry-run            print the plan and exit (no network, no writes)
#
# Environment:
#   EMBED_URL            override the download URL entirely
#   SKIP_RUNTIME=1       caller may skip; this script exits 0 without doing work
#
# This is best-effort automation. If the download or the pip bootstrap is not
# possible (offline, non-Windows host), it prints clear manual steps and exits
# non-zero so the caller can fall back to manual staging.
set -euo pipefail

RUNTIME_DIR="${1:-}"
if [ -z "$RUNTIME_DIR" ]; then
  echo "error: <runtime_dir> is required" >&2
  exit 2
fi
shift || true

VERSION=""
ARCH="amd64"
REQUIREMENTS=""
APP_REL="../app"
DRY_RUN=0
NO_DEPS=0

while [ $# -gt 0 ]; do
  case "$1" in
    --version) VERSION="${2:-}"; shift 2 ;;
    --arch) ARCH="${2:-}"; shift 2 ;;
    --requirements) REQUIREMENTS="${2:-}"; shift 2 ;;
    --app-rel) APP_REL="${2:-}"; shift 2 ;;
    --no-deps) NO_DEPS=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    *) echo "error: unknown option: $1" >&2; exit 2 ;;
  esac
done

if [ "${SKIP_RUNTIME:-0}" = "1" ]; then
  echo "==> SKIP_RUNTIME=1: not fetching an embedded Python."
  exit 0
fi

# Resolve the version: explicit > host interpreter > a known-good fallback.
if [ -z "$VERSION" ]; then
  if command -v python3 >/dev/null 2>&1; then
    VERSION="$(python3 -c 'import sys;print("%d.%d.%d"%sys.version_info[:3])' 2>/dev/null || true)"
  fi
  if [ -z "$VERSION" ] && command -v python >/dev/null 2>&1; then
    VERSION="$(python -c 'import sys;print("%d.%d.%d"%sys.version_info[:3])' 2>/dev/null || true)"
  fi
  VERSION="${VERSION:-3.12.7}"
fi

PYXY="$(printf '%s' "$VERSION" | cut -d. -f1,2 | tr -d '.')"
ZIP_NAME="python-${VERSION}-embed-${ARCH}.zip"
URL="${EMBED_URL:-https://www.python.org/ftp/python/${VERSION}/${ZIP_NAME}}"
PTH_FILE="${RUNTIME_DIR}/python${PYXY}._pth"

echo "==> Embedded Python : $VERSION ($ARCH)"
echo "==> Runtime dir     : $RUNTIME_DIR"
echo "==> Download URL    : $URL"

if [ "$DRY_RUN" = "1" ]; then
  echo "==> Dry run: would unzip into $RUNTIME_DIR and write $PTH_FILE with:"
  echo "      python${PYXY}.zip"
  echo "      ."
  echo "      ${APP_REL}"
  echo "      site-packages"
  echo "      import site"
  [ -n "$REQUIREMENTS" ] && echo "==> Dry run: would pip install -r $REQUIREMENTS"
  exit 0
fi

# Pick a downloader.
if command -v curl >/dev/null 2>&1; then
  download() { curl -fsSL "$1" -o "$2"; }
elif command -v wget >/dev/null 2>&1; then
  download() { wget -q "$1" -O "$2"; }
else
  echo "error: neither curl nor wget is available; cannot download the runtime." >&2
  exit 3
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "==> Downloading embeddable package"
if ! download "$URL" "$TMP/$ZIP_NAME"; then
  cat >&2 <<EOF
error: could not download $URL

Manual steps (offline / restricted network):
  1. Download "${ZIP_NAME}" from https://www.python.org/downloads/windows/
  2. Unzip it into: $RUNTIME_DIR
  3. Create "$PTH_FILE" with:
       python${PYXY}.zip
       .
       ${APP_REL}
       site-packages
       import site
  4. Install dependencies into "$RUNTIME_DIR/site-packages".
EOF
  exit 4
fi

mkdir -p "$RUNTIME_DIR"

echo "==> Unzipping into runtime/"
if command -v unzip >/dev/null 2>&1; then
  unzip -o -q "$TMP/$ZIP_NAME" -d "$RUNTIME_DIR"
else
  # python's zipfile is always available as a fallback.
  python3 - "$TMP/$ZIP_NAME" "$RUNTIME_DIR" <<'PY'
import sys, zipfile
with zipfile.ZipFile(sys.argv[1]) as z:
    z.extractall(sys.argv[2])
PY
fi

# The ._pth replaces sys.path; add the app dir and our site-packages.
cat > "$PTH_FILE" <<EOF
python${PYXY}.zip
.
${APP_REL}
site-packages
import site
EOF
echo "==> Wrote $PTH_FILE"

# Bootstrap pip and install dependencies only if we can run the embedded
# interpreter (i.e. we are on Windows). Otherwise leave a clear next step.
PY_EXE="$RUNTIME_DIR/python.exe"
if [ "$NO_DEPS" = "1" ]; then
  echo "==> --no-deps: skipping dependency installation (caller stages wheels)."
elif [ -x "$PY_EXE" ] || { [ -f "$PY_EXE" ] && command -v "$PY_EXE" >/dev/null 2>&1; }; then
  if [ -n "$REQUIREMENTS" ] && [ -f "$REQUIREMENTS" ]; then
    echo "==> Bootstrapping pip into the embedded runtime"
    if download "https://bootstrap.pypa.io/get-pip.py" "$TMP/get-pip.py"; then
      "$PY_EXE" "$TMP/get-pip.py" --no-warn-script-location >/dev/null 2>&1 || \
        echo "warning: get-pip bootstrap failed; install dependencies manually."
      echo "==> Installing dependencies into site-packages"
      "$PY_EXE" -m pip install --no-cache-dir --no-warn-script-location \
        --target "$RUNTIME_DIR/site-packages" -r "$REQUIREMENTS" || \
        echo "warning: dependency install failed; run it manually."
    else
      echo "warning: could not download get-pip.py; install dependencies manually."
    fi
  fi
else
  cat <<EOF
==> Embedded interpreter cannot be executed on this host.
    Dependencies were NOT installed. On Windows (or with the embedded
    python.exe runnable), install them with:
      "$RUNTIME_DIR/python.exe" -m pip install --target "$RUNTIME_DIR/site-packages" -r <requirements>
EOF
fi

echo "==> Embedded runtime staged at $RUNTIME_DIR"
