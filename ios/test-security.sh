#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
task_tmp=$(mktemp -d "${TMPDIR:-/tmp}/carelink-security.XXXXXX")
trap 'rm -rf "$task_tmp"' EXIT HUP INT TERM
swiftc -parse-as-library -module-cache-path "$task_tmp/modules" \
 "$root/ios/CareLink/Models.swift" "$root/ios/CareLink/Monitoring.swift" \
 "$root/ios/CareLink/Services.swift" "$root/ios/CareLink/InteractionModels.swift" \
 "$root/ios/CareLink/SessionCredentials.swift" "$root/ios/CareLink/SecureTransport.swift" \
 "$root/ios/CareLink/LiveApiService.swift" "$root/ios/CoreTests/MemorySessionStore.swift" \
 "$root/ios/CoreTests/SecurityChecks.swift" -o "$task_tmp/security-checks"
"$task_tmp/security-checks" "$root/shared"
