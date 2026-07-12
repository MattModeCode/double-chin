#!/usr/bin/env bash
# Build dist/ChinAI.app — the self-contained macOS desktop app.
#
# Usage: bash packaging/build_app.sh
#
# The result is ad-hoc signed so it launches on this machine. It is NOT
# notarized (that needs an Apple Developer ID, out of scope for a personal
# app) — first launch needs one right-click -> Open to satisfy Gatekeeper,
# or: xattr -dr com.apple.quarantine dist/ChinAI.app
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

VENV_PYTHON=".venv/bin/python"
if [ ! -x "$VENV_PYTHON" ]; then
  echo "error: $VENV_PYTHON not found." >&2
  echo "  Run first: uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -e \".[dev]\"" >&2
  exit 1
fi

if ! "$VENV_PYTHON" -m PyInstaller --version >/dev/null 2>&1; then
  echo "Installing PyInstaller into .venv (build-time only, not a runtime dependency)..."
  # This repo's .venv is uv-managed and has no bundled pip; use uv directly.
  # `command -v uv` can resolve to a stale/wrong-arch shim earlier on PATH
  # than the real one, so probe candidates by actually running them.
  UV_BIN=""
  for candidate in /opt/homebrew/bin/uv /usr/local/bin/uv "$(command -v uv 2>/dev/null || true)"; do
    if [ -n "$candidate" ] && "$candidate" --version >/dev/null 2>&1; then
      UV_BIN="$candidate"
      break
    fi
  done
  if [ -n "$UV_BIN" ]; then
    "$UV_BIN" pip install --python "$VENV_PYTHON" pyinstaller
  else
    "$VENV_PYTHON" -m pip install pyinstaller
  fi
fi

rm -rf build dist

"$VENV_PYTHON" -m PyInstaller packaging/chinai.spec --noconfirm

APP="dist/ChinAI.app"
if [ ! -d "$APP" ]; then
  echo "error: build did not produce $APP" >&2
  exit 1
fi

# Ad-hoc sign (no Apple Developer ID) so the app launches on this machine.
codesign --force --deep --sign - "$APP"

echo
echo "Built $APP"
echo "First launch needs one of:"
echo "  - right-click $APP -> Open (Gatekeeper prompt for an unsigned app), or"
echo "  - xattr -dr com.apple.quarantine \"$APP\""
