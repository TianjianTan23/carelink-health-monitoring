#!/bin/zsh
set -e
cd -- "$(dirname -- "$0")"
exec ./start-without-hardware.command
