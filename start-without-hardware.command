#!/bin/zsh
set -e
cd -- "$(dirname -- "$0")"
if ! sh scripts/configure-accounts.sh --check; then sh scripts/configure-accounts.sh; fi
if [[ ! -d node_modules ]]; then npm ci; fi
npm run build
exec sh scripts/python-local.sh scripts/run-without-hardware.py
