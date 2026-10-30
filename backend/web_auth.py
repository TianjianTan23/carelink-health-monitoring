"""Durable Web identities, Argon2id and revocable opaque sessions.

No service is started here. Keep the database and all SQLite sidecars private.
Legacy PBKDF2 is accepted only for gradual, successful-login migration.
ttj/wyn keep their existing passwords. Migration changes only the stored hash;
the historical needs_password_rotation field is not a login/reset requirement.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import stat
import threading
import time

from argon2 import PasswordHasher, Type, extract_parameters
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=1,
                        hash_len=32, salt_len=16, type=Type.ID)
HASH_SLOTS = threading.BoundedSemaphore(2)
DUMMY_HASH = HASHER.hash(secrets.token_bytes(32))
DUMMY_LEGACY = "pbkdf2_sha256$310000$" + "00" * 16 + "$" + "00" * 32
TOKEN_RE = re.compile(r"cl_s1_[A-Za-z0-9_-]{43}\Z")
TTL = 8 * 60 * 60
WINDOW = 15 * 60
MAX_BUCKETS = 4096


def _hash_kind(encoded):
    """Bounded allowlist; never treat an arbitrary string as a stored hash."""
    if not isinstance(encoded, str) or len(encoded) >= 1024:
        return None
    if encoded.startswith("pbkdf2_sha256$"):
        try:
            _, rounds, salt, digest = encoded.split("$")
            if (rounds.isascii() and rounds.isdigit() and 10000 <= int(rounds) <= 1000000
                    and re.fullmatch(r"[0-9a-f]{32}",salt) and re.fullmatch(r"[0-9a-f]{64}",digest)):
                return "legacy"
        except ValueError:
            pass
    elif encoded.startswith("$argon2id$"):
        try:
            p = extract_parameters(encoded)
            if (p.type == Type.ID and p.version == 19 and 8192 <= p.memory_cost <= 131072
                    and 1 <= p.time_cost <= 6 and 1 <= p.parallelism <= 4
                    and 16 <= p.salt_len <= 64 and 16 <= p.hash_len <= 64
                    and all(re.fullmatch(r"[A-Za-z0-9+/]+",part) for part in encoded.split("$")[-2:])):
                return "argon"
        except (InvalidHashError, ValueError):
            pass
    return None


def verify_password(password: str, encoded: str) -> tuple[bool, bool]:
    """Return (valid, needs_upgrade), bounding hash work and memory.

    Failed known/unknown logins both perform one PBKDF2 and one Argon2 check.
    Equal errors and comparable work reduce enumeration; timing is not a proof
    of indistinguishability. Rate limits bound work before this function.
    """
    if not HASH_SLOTS.acquire(blocking=False):
        raise HTTPException(503, "Authentication temporarily unavailable")
    try:
        valid = False
        kind = _hash_kind(encoded)
        legacy, argon = kind == "legacy", kind == "argon"
        if legacy:
            _, rounds, salt, digest = encoded.split("$")
            actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds)).hex()
            valid = hmac.compare_digest(actual, digest)
        if not legacy:
            hashlib.pbkdf2_hmac("sha256", password.encode(), bytes(16), 310000)
        try:
            checked = HASHER.verify(encoded if argon else DUMMY_HASH, password)
            if argon:
                valid = checked
        except (VerificationError, InvalidHashError, ValueError):
            if argon:
                valid = False
        return valid, valid and (legacy or HASHER.check_needs_rehash(encoded))
    finally:
        HASH_SLOTS.release()


def hash_password(password: str) -> str:
    if not 12 <= len(password) <= 1024 or len(password.encode()) > 1024:
        raise ValueError("Use 12–1024 UTF-8 bytes for the new password")
    with HASH_SLOTS:
        return HASHER.hash(password)


def token_hash(token):
    if not isinstance(token, str) or not TOKEN_RE.fullmatch(token):
        return None
    return hashlib.sha256(token.encode("ascii")).hexdigest()


class AuthStore:
    def __init__(self, path=None, *, clock=time.time):
        self.path = Path(path or os.environ.get("CARELINK_AUTH_DATABASE_PATH", ROOT / ".secrets/web-auth.sqlite3")).absolute()
        from .storage_paths import validate_storage_paths
        validate_storage_paths(auth=self.path)
        self.clock = clock
        self.marker = self.path.with_suffix(self.path.suffix + ".initialized")

    def _private_storage(self):
        # The immediate directory must be owned by the gateway operator. Do not
        # silently chmod an accidentally selected database or follow aliases.
        for path, directory in [(self.path.parent, True)] + [
            (p, False) for p in (self.path, self.marker, Path(str(self.path)+"-wal"), Path(str(self.path)+"-shm"))
        ]:
            try:
                info = path.lstat()
            except FileNotFoundError:
                continue
            expected = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
            if (not expected or info.st_uid != os.getuid() or info.st_mode & 0o077
                    or (not directory and info.st_nlink != 1)):
                raise RuntimeError("Authentication storage must be private, owned and unaliased")

    @contextmanager
    def connect(self, *, create=False):
        try:
            self._private_storage()
            if not self.path.is_file() or (not create and (not self.marker.is_file() or self.path.stat().st_size < 512)):
                raise RuntimeError("Authentication storage missing")
            db = sqlite3.connect(self.path.as_uri()+"?mode=rw", uri=True, timeout=15)
            try:
                db.row_factory = sqlite3.Row
                db.execute("PRAGMA foreign_keys=ON")
                db.execute("PRAGMA busy_timeout=15000")
                db.execute("PRAGMA synchronous=FULL")
                yield db
            finally:
                db.close()
        except (sqlite3.Error, OSError, RuntimeError):
            # No database paths, SQL parameters or credentials in public errors.
            raise HTTPException(503, "Authentication storage unavailable") from None

    def initialize(self, accounts):
        self.path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        self._private_storage()
        if self.marker.exists() and (not self.path.exists() or self.path.stat().st_size < 512):
            raise RuntimeError("Auth database is missing/truncated; restore its private backup, do not reseed")
        initialized = self.marker.exists()
        if not initialized and self.path.exists() and self.path.stat().st_size:
            raise RuntimeError("Unmarked auth database; inspect/restore it instead of reseeding")
        if not initialized:
            for username, account in accounts.items():
                if (not isinstance(username,str) or not re.fullmatch(r"[a-z0-9_.-]{1,64}",username)
                        or _hash_kind(account.get("password_hash")) is None
                        or account.get("role") not in {"patient","clinician"}
                        or not isinstance(account.get("mode"),str)
                        or not 1 <= len(account["mode"]) <= 64
                        or not isinstance(account.get("patient_ids"),list)
                        or len(account["patient_ids"]) > 256
                        or any(not isinstance(p,str) or not 1 <= len(p) <= 128 for p in account["patient_ids"])
                        or account.get("needs_password_rotation",1) not in (0,1)):
                    raise RuntimeError("Invalid private account bootstrap")
        if not self.path.exists():
            # SQLite and its sidecars inherit 0600 from the start, before any
            # password verifier is stored, regardless of the process umask.
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            os.close(fd)
        with self.connect(create=True) as db:
            db.execute("PRAGMA journal_mode=WAL")
            if initialized:
                expected = {"users": {"username", "password_hash", "role", "mode", "patient_ids", "active", "needs_password_rotation", "created_at", "updated_at"},
                            "sessions": {"token_hash", "username", "created_at", "expires_at", "revoked_at", "replacement_hash"},
                            "login_limits": {"bucket_hash", "window_start", "attempts"}}
                for table, columns in expected.items():
                    if not columns <= {r[1] for r in db.execute(f"PRAGMA table_info({table})")}:
                        raise RuntimeError("Auth database schema is incomplete; restore its private backup")
                # Once initialized, deleted accounts are never recreated from
                # stale bootstrap data; the durable DB is authoritative.
                return
            db.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY, password_hash TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('patient','clinician')),
                    mode TEXT NOT NULL, patient_ids TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    needs_password_rotation INTEGER NOT NULL DEFAULT 1,
                    created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY, username TEXT NOT NULL REFERENCES users(username),
                    created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
                    revoked_at INTEGER, replacement_hash TEXT);
                CREATE INDEX IF NOT EXISTS sessions_user ON sessions(username);
                CREATE TABLE IF NOT EXISTS login_limits (
                    bucket_hash TEXT PRIMARY KEY, window_start INTEGER NOT NULL, attempts INTEGER NOT NULL);
            """)
            now = int(self.clock())
            # Existing identities/passwords/scopes are never overwritten on startup.
            with db:
                for username, a in accounts.items():
                    db.execute("INSERT OR IGNORE INTO users(username,password_hash,role,mode,patient_ids,needs_password_rotation,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                               (username, a["password_hash"], a["role"], a["mode"], json.dumps(a["patient_ids"]), a.get("needs_password_rotation", 1), now, now))
        fd = os.open(self.marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        directory = os.open(self.path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)

    def account(self, username):
        with self.connect() as db:
            r = db.execute("SELECT * FROM users WHERE username=? AND active=1", (username,)).fetchone()
        if not r:
            raise HTTPException(401, "Authentication required")
        a = dict(r)
        a["patient_ids"] = json.loads(a["patient_ids"])
        return a

    def reserve_login(self, username, peer):
        now = int(self.clock())
        limits = (20, 10, 5)
        # Test deployments may raise a bounded limit; production default is 5/10/20.
        override = os.environ.get("CARELINK_LOGIN_TEST_LIMIT")
        if override:
            n = int(override)
            if not 1 <= n <= 100:
                raise RuntimeError("Login limit must be within 1..100")
            limits = (n, n, n)
        pairs = zip((f"ip:{peer}", f"account:{username}", f"pair:{peer}:{username}"), limits)
        buckets = [(hashlib.sha256(s.encode()).hexdigest(), n) for s, n in pairs]
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM login_limits WHERE window_start<=?", (now-WINDOW,))
            rows = {r["bucket_hash"]: r for r in db.execute("SELECT * FROM login_limits")}
            full = len(rows) + sum(k not in rows for k, _ in buckets) > MAX_BUCKETS
            blocked = [rows[k]["window_start"]+WINDOW-now for k, n in buckets
                       if k in rows and rows[k]["attempts"] >= n]
            denied = full or bool(blocked)
            # Capacity frees at the earliest expiry. All blocking buckets must
            # expire, so their longest wait governs a normal rate-limit denial.
            retry = max(blocked, default=1)
            if full:
                retry = max(retry, min(r["window_start"]+WINDOW-now for r in rows.values()))
            if not denied:
                for key, _ in buckets:
                    db.execute("INSERT INTO login_limits VALUES(?,?,1) ON CONFLICT(bucket_hash) DO UPDATE SET attempts=attempts+1", (key, now))
            db.commit()
        if denied:
            raise HTTPException(429, "Too many login attempts; try later", headers={"Retry-After":str(max(1, retry))})

    def login(self, username, password, peer, old_token=None):
        username = username.strip().lower()
        self.reserve_login(username, peer)
        for _ in range(2):
            with self.connect() as db:
                row = db.execute("SELECT * FROM users WHERE username=? AND active=1", (username,)).fetchone()
            encoded = row["password_hash"] if row else ""
            valid, upgrade = verify_password(password, encoded)
            if not row or not valid:
                raise HTTPException(401, "Invalid user ID or password")
            replacement = hash_password_for_migration(password) if upgrade else encoded
            token = "cl_s1_" + secrets.token_urlsafe(32)
            now = int(self.clock())
            with self.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                # Atomic compare-and-swap: a concurrent migration/credential
                # update or account disable must never be overwritten. The
                # loser rereads and verifies the submitted original password
                # against the CURRENT hash before creating any session.
                changed = db.execute("UPDATE users SET password_hash=?,updated_at=? WHERE username=? AND password_hash=? AND active=1",
                                     (replacement, now, username, encoded)).rowcount
                if changed != 1:
                    db.rollback()
                    continue
                if old := token_hash(old_token):
                    db.execute("UPDATE sessions SET revoked_at=COALESCE(revoked_at,?) WHERE token_hash=?", (now, old))
                db.execute("INSERT INTO sessions(token_hash,username,created_at,expires_at) VALUES(?,?,?,?)", (token_hash(token), username, now, now+TTL))
                db.commit()
            return token
        raise HTTPException(401, "Invalid user ID or password")

    def username(self, token):
        digest = token_hash(token)
        if digest is None:
            return None
        with self.connect() as db:
            row = db.execute("SELECT s.username FROM sessions s JOIN users u USING(username) WHERE token_hash=? AND revoked_at IS NULL AND expires_at>? AND u.active=1", (digest, int(self.clock()))).fetchone()
        return row[0] if row else None

    def revoke(self, token):
        if digest := token_hash(token):
            with self.connect() as db, db:
                db.execute("UPDATE sessions SET revoked_at=COALESCE(revoked_at,?) WHERE token_hash=?", (int(self.clock()), digest))

    def rotate(self, token):
        digest = token_hash(token)
        new_token = "cl_s1_" + secrets.token_urlsafe(32)
        now = int(self.clock())
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT s.* FROM sessions s JOIN users u USING(username) WHERE token_hash=? AND revoked_at IS NULL AND expires_at>? AND u.active=1", (digest, now)).fetchone()
            if not row:
                raise HTTPException(401, "Authentication required")
            db.execute("UPDATE sessions SET revoked_at=?,replacement_hash=? WHERE token_hash=?", (now, token_hash(new_token), digest))
            db.execute("INSERT INTO sessions(token_hash,username,created_at,expires_at) VALUES(?,?,?,?)", (token_hash(new_token), row["username"], now, row["expires_at"]))
            db.commit()
        return new_token, row["expires_at"]-now

    def change_password(self, username, password):
        self.replace_password_hash(username, hash_password(password))

    def replace_password_hash(self, username, encoded):
        # Operator-only internal path; never exposed as an HTTP route.
        try:
            if _hash_kind(encoded) != "argon" or HASHER.check_needs_rehash(encoded):
                raise ValueError("Invalid replacement policy")
        except (InvalidHashError, TypeError, AttributeError):
            raise ValueError("Invalid replacement policy") from None
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            changed = db.execute("UPDATE users SET password_hash=?,needs_password_rotation=0,updated_at=? WHERE username=?", (encoded, int(self.clock()), username)).rowcount
            if changed != 1:
                raise ValueError("Unknown account")
            db.execute("UPDATE sessions SET revoked_at=COALESCE(revoked_at,?) WHERE username=?", (int(self.clock()), username))
            db.commit()


def hash_password_for_migration(password):
    # Rehash the verified original password, including legacy short passwords.
    # Do not apply new-password policy or force a reset during login migration.
    with HASH_SLOTS:
        return HASHER.hash(password)


def store():
    try:return AuthStore()
    except RuntimeError:raise HTTPException(503,"Authentication storage unavailable") from None


def bootstrap_accounts(accounts):
    """One-time compatibility import, never a public default credential.

    After initialization, the DB is authoritative; the bootstrap file is no
    longer read. Neither startup nor environment overrides reset existing users.
    """
    result = {username:dict(account) for username, account in accounts.items()}
    for username, variable in (("ttj", "CARELINK_PATIENT_PASSWORD_HASH"), ("wyn", "CARELINK_NURSE_PASSWORD_HASH")):
        if username in result and variable in os.environ:
            result[username]["password_hash"] = os.environ[variable]
    missing = [u for u,a in result.items() if not a.get("password_hash")]
    if missing:
        path = Path(os.environ.get("CARELINK_WEB_BOOTSTRAP_FILE", ROOT / ".secrets/web-bootstrap.json"))
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, "r", encoding="utf-8") as source:
                info = os.fstat(source.fileno())
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                        or info.st_nlink != 1 or info.st_mode & 0o077 or info.st_size > 32768):
                    raise ValueError("Unsafe bootstrap file")
                data = json.loads(source.read(32769))
            if data["version"] != 1:
                raise ValueError("Unknown bootstrap version")
            for username in missing:
                result[username]["password_hash"] = data["users"][username]["password_hash"]
        except (OSError, ValueError, KeyError, TypeError):
            raise RuntimeError("Private password bootstrap missing/unsafe; refuse public default accounts") from None
    for account in result.values():
        encoded = account.get("password_hash")
        if _hash_kind(encoded) is None:
            raise RuntimeError("Invalid private password bootstrap")
    return result
