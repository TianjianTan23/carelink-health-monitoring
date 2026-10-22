#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
task_tmp=$(mktemp -d "${TMPDIR:-/tmp}/carelink-core.XXXXXX")
trap 'rm -rf "$task_tmp"' EXIT HUP INT TERM
swiftc -parse-as-library -module-cache-path "$task_tmp/modules" \
  "$task_root/ios/CareLink/Models.swift" \
  "$task_root/ios/CareLink/Monitoring.swift" \
  "$task_root/ios/CareLink/Services.swift" \
  "$task_root/ios/CareLink/LiveApiService.swift" \
  "$task_root/ios/CareLink/InteractionModels.swift" \
  "$task_root/ios/CoreTests/CoreChecks.swift" \
  -o "$task_tmp/carelink-core-checks"
"$task_tmp/carelink-core-checks" "$task_root/shared"
