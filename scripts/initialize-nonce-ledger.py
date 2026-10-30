#!/usr/bin/env python3
"""NEW installation only. Not a recovery/upgrade/reset utility. No default path."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.nonce_ledger import AUTHORIZATION, initialize_new_ledger
from backend.device_auth_errors import DeviceAuthError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--new-installation", required=True, type=Path, metavar="ABSOLUTE_NEW_PATH")
    args = parser.parse_args()
    if not sys.stdin.isatty() or not args.new_installation.is_absolute():
        print("FAIL: interactive local terminal and absolute NEW path required.")
        return 1
    print("Only for an authorized NEW installation; NEVER for a missing existing ledger.")
    print("Existing files and incomplete attempts will be refused, never overwritten.")
    print("Target:", args.new_installation)
    if input("Type CREATE A NEW INSTALLATION LEDGER to authorize: ") != AUTHORIZATION:
        print("FAIL: not authorized; nothing initialized.")
        return 1
    try:
        initialize_new_ledger(args.new_installation, authorization=AUTHORIZATION)
    except DeviceAuthError:
        print("FAIL: initialization unavailable; preserve artifacts for manual review.")
        return 1
    print("PASS: new installation ledger initialized. No credentials generated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
