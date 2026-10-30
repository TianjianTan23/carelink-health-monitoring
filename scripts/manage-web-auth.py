#!/usr/bin/env python3
"""Explicit local password preparation/rotation; never deploys a service.

prepare creates a NEW offline account DB after all passwords are validated.
rotate changes ONE account in an EXISTING DB and revokes its sessions.
Passwords are never accepted via arguments, environment variables or pipes.
This optional manual tool is not part of the ttj/wyn deployment plan: those
accounts keep their existing passwords through successful-login migration.
"""
import argparse
from getpass import getpass, GetPassWarning
from pathlib import Path
import sys
import warnings
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.web_auth import AuthStore, hash_password


def read_password(username, prompt=getpass):
    with warnings.catch_warnings():
        warnings.simplefilter("error", GetPassWarning)
        first = prompt(f"New password for {username} (12+ characters; hidden): ")
        second = prompt("Repeat new password (hidden): ")
    if first != second:
        raise ValueError("Password confirmation failed")
    return hash_password(first)


def prepare(path, accounts, prompt=getpass):
    target = AuthStore(path)
    if any(p.exists() or p.is_symlink() for p in (
        target.path, target.marker, Path(str(target.path)+"-wal"), Path(str(target.path)+"-shm")
    )):
        raise ValueError("Preparation requires a new target")
    # No DB writes or legacy import until ALL entries pass confirmation/policy.
    prepared = {}
    for username, account in accounts.items():
        prepared[username] = {"role": account["role"], "mode": account["mode"],
                              "patient_ids": list(account["patient_ids"]),
                              "password_hash": read_password(username, prompt),
                              "needs_password_rotation": 0}
    target.initialize(prepared)


def rotate(path, username, prompt=getpass):
    target = AuthStore(path)
    target.account(username)
    target.replace_password_hash(username, read_password(username, prompt))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "rotate"))
    parser.add_argument("--database", required=True, type=Path,
                        help="Explicit absolute path; no implicit production DB")
    parser.add_argument("--username", help="Existing username; required for rotate")
    args = parser.parse_args(argv)
    if not args.database.is_absolute():
        parser.error("An absolute database path is required")
    if (args.operation == "rotate") != bool(args.username):
        parser.error("Only rotate requires --username")
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        parser.exit(1, "FAIL: local interactive terminal required; no change made.\n")
    print(f"Target database: {args.database}")
    print("This does not deploy or restart any service.")
    try:
        confirmation = input(f"Type {args.operation.upper()} to confirm this target: ")
        if confirmation != args.operation.upper():
            parser.exit(1, "FAIL: cancelled; no change made.\n")
        if args.operation == "prepare":
            from backend.app import USERS
            prepare(args.database, USERS)  # Only public role/scope metadata copied.
        else:
            rotate(args.database, args.username.strip().lower())
    except (Exception, KeyboardInterrupt):
        # No exception text, SQL values, password input or verifiers in output.
        parser.exit(1, "FAIL: operation not completed; inspect target status before retrying. No service changed.\n")
    print("PASS: account operation completed. Rotation revokes this account's sessions.")


if __name__ == "__main__":
    main()
