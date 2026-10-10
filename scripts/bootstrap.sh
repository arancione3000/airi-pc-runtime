#!/usr/bin/env bash
set -euo pipefail
WORKSPACE_ROOT="${AIRIPC_WORKSPACE_ROOT:-/home/user/airi}"
VENV="${AIRIPC_VENV:-$WORKSPACE_ROOT/.venv}"
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-$WORKSPACE_ROOT/.cache/ms-playwright}"
mkdir -p "$WORKSPACE_ROOT/projects" "$WORKSPACE_ROOT/state" "$WORKSPACE_ROOT/logs" "$WORKSPACE_ROOT/config"
if [[ ! -x "$VENV/bin/python" ]]; then python3 -m venv "$VENV"; fi
"$VENV/bin/python" -m pip install --disable-pip-version-check --quiet -r "$WORKSPACE_ROOT/computer/requirements.txt"
"$VENV/bin/python" -m playwright install chromium
find "$WORKSPACE_ROOT/scripts" -maxdepth 1 -type f -name 'airi-*' -exec chmod u+x {} +
chmod u+x "$WORKSPACE_ROOT/computer/start.sh"
printf 'Airi-PC runtime dependencies ready: %s\n' "$WORKSPACE_ROOT"
