#!/usr/bin/env python3
"""Check local secrets against shareable files and Git history; print paths only."""
import json
from pathlib import Path
import re
import subprocess
import sys
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
known = set()

def remember(value):
    if isinstance(value, str) and len(value) >= 8 and not value.startswith(("SET_LOCALLY", "GENERATED_", "YOUR_")):
        known.add(value.encode())

for path in (ROOT / "firmware/elder_sensors/secrets.h", ROOT.parent / "esp32/elder_sensors/secrets.h"):
    if path.exists():
        text = path.read_text()
        for name in ("WIFI_PASSWORD", "DEVICE_API_KEY", "DEVICE_HMAC_SECRET"):
            match = re.search(r'\b' + name + r'\s*=\s*("(?:\\.|[^"\\])*")\s*;', text)
            if match:
                try:
                    remember(json.loads(match.group(1)))
                except ValueError:
                    pass
if (ROOT / ".env").exists():
    config = dotenv_values(ROOT / ".env", interpolate=False)
    remember(config.get("CARELINK_SESSION_SECRET"))
    try:
        for keys in json.loads(config.get("CARELINK_DEVICES") or "{}").values():
            for value in keys.values():
                remember(value)
    except (ValueError, AttributeError):
        pass

def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args])

current = []
for name in git("ls-files", "-c", "-o", "--exclude-standard", "-z").split(b"\0"):
    if not name:
        continue
    path = ROOT / name.decode()
    if path.is_file() and any(value in path.read_bytes() for value in known):
        current.append(name.decode())

historical = []
for line in git("rev-list", "--objects", "--all").decode().splitlines():
    parts = line.split(" ", 1)
    if len(parts) != 2:
        continue
    oid, path = parts
    if git("cat-file", "-t", oid).strip() != b"blob":
        continue
    data = git("cat-file", "blob", oid)
    if any(value in data for value in known):
        historical.append(path)

print(f"Current shareable files matching local secret values: {len(set(current))}")
print(f"Historical file paths matching local secret values: {len(set(historical))}")
for path in sorted(set(current + historical)):
    print("Review path:", path)
print("Secret values were not displayed. This exact-match check is not a general secret scanner.")
sys.exit(bool(current or historical))
