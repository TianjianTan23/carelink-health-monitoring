#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
task_tmp=$(mktemp -d "${TMPDIR:-/tmp}/carelink-native-tls.XXXXXX")
trap 'rm -rf "$task_tmp"' EXIT HUP INT TERM
swiftc -parse-as-library -module-cache-path "$task_tmp/modules" \
 "$root/ios/CareLink/Models.swift" "$root/ios/CareLink/Monitoring.swift" \
 "$root/ios/CareLink/Services.swift" "$root/ios/CareLink/InteractionModels.swift" \
 "$root/ios/CareLink/SessionCredentials.swift" "$root/ios/CareLink/SecureTransport.swift" \
 "$root/ios/CareLink/LiveApiService.swift" "$root/ios/CoreTests/MemorySessionStore.swift" \
 "$root/ios/TLSChecks/TLSChecks.swift" -o "$task_tmp/tls-checks"
PYTHONDONTWRITEBYTECODE=1 "$root/.venv/bin/python" "$root/scripts/test-ios-tls.py" "$task_tmp/tls-checks"
