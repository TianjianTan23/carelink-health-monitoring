#!/bin/sh
set -eu
PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$PROJECT_DIR"
PYTHON_EXECUTABLE="${CARELINK_PYTHON:-$PROJECT_DIR/../server/.venv/bin/python}"
if [ ! -x "$PYTHON_EXECUTABLE" ]; then
  if [ ! -x .venv/bin/python ]; then python3 -m venv .venv; fi
  PYTHON_EXECUTABLE="$PROJECT_DIR/.venv/bin/python"
fi
"$PYTHON_EXECUTABLE" -c 'import fastapi, uvicorn, torch, sklearn, argon2, dotenv' 2>/dev/null || "$PYTHON_EXECUTABLE" -m pip install -r backend/requirements.txt
exec "$PYTHON_EXECUTABLE" "$@"
