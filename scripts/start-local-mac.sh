#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$PROJECT_DIR"

PYTHON_COMMAND=${CARELINK_PYTHON:-python3}

if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
  echo "CareLink needs Node.js 22.19 or newer. Install Node.js, then run npm start again." >&2
  exit 1
fi

if ! command -v "$PYTHON_COMMAND" >/dev/null 2>&1; then
  echo "CareLink needs Python 3.10 or newer. Install Python 3, then run npm start again." >&2
  exit 1
fi

if ! "$PYTHON_COMMAND" --version >/dev/null 2>&1; then
  echo "Python could not start. On macOS, install Python from python.org/Homebrew or accept the Xcode licence, then retry." >&2
  exit 1
fi

if [ ! -x .venv/bin/python ]; then
  echo "[CareLink] Creating the Python virtual environment..."
  "$PYTHON_COMMAND" -m venv .venv
fi

REQUIREMENTS_HASH=$(shasum -a 256 backend/requirements.txt | awk '{print $1}')
INSTALLED_HASH=$(cat .venv/.carelink-requirements-sha256 2>/dev/null || true)
if [ "$REQUIREMENTS_HASH" != "$INSTALLED_HASH" ]; then
  echo "[CareLink] Installing the FastAPI and model dependencies..."
  .venv/bin/python -m pip install -r backend/requirements.txt
  printf '%s\n' "$REQUIREMENTS_HASH" > .venv/.carelink-requirements-sha256
fi

if [ ! -d node_modules ]; then
  echo "[CareLink] Installing the web dependencies..."
  npm ci
fi

echo "[CareLink] Building the live web application..."
npm run build

LAN_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)
echo ""
echo "CareLink LIVE is starting. Keep this Terminal window open."
echo "Mac browser: http://127.0.0.1:8000"
if [ -n "$LAN_IP" ]; then
  echo "Phone / another computer: http://$LAN_IP:8000"
  echo "ESP32 upload URL: http://$LAN_IP:8000/sensor-data"
fi
echo "Health check: http://127.0.0.1:8000/health"
echo "No readings will change until the ESP32 or npm run simulate:sensors sends data."
echo ""

exec .venv/bin/python -m uvicorn backend.app:app --host 0.0.0.0 --port 8000
