#!/bin/sh
set -eu
cd -- "$(dirname -- "$0")/.."
if ! sh scripts/configure-accounts.sh --check; then sh scripts/configure-accounts.sh; fi
if [ ! -d node_modules ]; then npm ci; fi
npm run build
printf '\nCareLink HTTP gateway: http://127.0.0.1:8000\n'
exec sh scripts/python-local.sh scripts/serve-local.py
