#!/usr/bin/env python3
"""Set local account passwords without generating certificates or device keys."""
import argparse
import getpass
import os
from pathlib import Path
import secrets
import sys
from dotenv import dotenv_values, set_key

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.security import HASHER, Security

def configured(config):
    checker = Security(None, {name: {"password_hash": config.get(key, "")} for name, key in
        (("ttj", "CARELINK_PATIENT_PASSWORD_HASH"), ("wyn", "CARELINK_NURSE_PASSWORD_HASH"))})
    checker.secret = config.get("CARELINK_SESSION_SECRET", "")
    try:
        checker.validate_configuration()
        return True
    except RuntimeError:
        return False

def configure(path, reset=False, prompt=getpass.getpass):
    previous = dict(dotenv_values(path, interpolate=False)) if path.exists() else {}
    if configured(previous) and not reset:
        return False
    passwords = {}
    for name, key in (("ttj", "CARELINK_PATIENT_PASSWORD_HASH"), ("wyn", "CARELINK_NURSE_PASSWORD_HASH")):
        first = prompt(f"{name} password (at least 12 characters): ")
        second = prompt(f"Confirm {name} password: ")
        if len(first) < 12 or first != second:
            raise ValueError("Passwords must match and contain at least 12 characters; nothing was saved.")
        passwords[key] = HASHER.hash(first)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(mode=0o600, exist_ok=True)
    path.chmod(0o600)
    for key, value in {"VITE_DATA_MODE": "live", "VITE_API_BASE_URL": "", "VITE_API_CONFIRMED": "true",
                       **passwords, "CARELINK_SESSION_SECRET": secrets.token_hex(32)}.items():
        set_key(str(path), key, value, quote_mode="always")
    path.chmod(0o600)
    return True

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--reset-passwords", action="store_true")
    args = parser.parse_args()
    path = Path(os.environ.get("CARELINK_ENV_FILE", ROOT / ".env"))
    if args.check:
        config = {**dict(dotenv_values(path, interpolate=False)), **os.environ}
        return 0 if configured(config) else 1
    try:
        changed = configure(path, args.reset_passwords)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1
    print("Account passwords saved locally." if changed else "Existing accounts retained; passwords unchanged.")
    print("HTTP mode: no certificate installation or device signature setup is needed.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
