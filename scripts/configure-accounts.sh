#!/bin/sh
set -eu
cd -- "$(dirname -- "$0")/.."
exec sh scripts/python-local.sh scripts/configure-accounts.py "$@"
