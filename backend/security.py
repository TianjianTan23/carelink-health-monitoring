"""Account sessions for the local HTTP coursework gateway. Never log bodies, cookies or credentials."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time

from argon2 import PasswordHasher, Type, extract_parameters
from argon2.exceptions import VerificationError, InvalidHashError
from dotenv import load_dotenv
from fastapi import HTTPException, Request
from starlette.responses import JSONResponse

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(os.environ.get("CARELINK_ENV_FILE", ROOT / ".env"), interpolate=False)
HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2, type=Type.ID)
DUMMY_HASH = HASHER.hash(secrets.token_urlsafe(32))
COOKIE = "carelink_session"
SESSION_SECONDS = 8 * 60 * 60
MAX_BODY = 128 * 1024
LOGIN_WINDOW = 15 * 60


def verify_password(password: str, encoded: str) -> bool:
    try:
        return encoded.startswith("$argon2id$") and HASHER.verify(encoded, password)
    except (VerificationError, InvalidHashError, ValueError, TypeError):
        return False


class Security:
    def __init__(self, connect, users):
        self.connect = connect
        self.users = users
        self.secret = os.environ.get("CARELINK_SESSION_SECRET", "")
    def validate_configuration(self):
        # Existing passwords stay hashed; no certificate or device key is needed.
        try:
            if len(bytes.fromhex(self.secret)) != 32:
                raise ValueError()
            for account in self.users.values():
                p = extract_parameters(account["password_hash"])
                if p.type != Type.ID or p.memory_cost < 19456 or p.time_cost < 2:
                    raise ValueError()
        except (ValueError, TypeError, KeyError, InvalidHashError):
            raise RuntimeError("Security configuration missing or invalid. Run scripts/configure-accounts.py; no secrets were logged.") from None

    def initialize(self):
        self.validate_configuration()
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS security_sessions (
                    token_hash TEXT PRIMARY KEY, username TEXT NOT NULL,
                    expires REAL NOT NULL, auth_version TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS security_logins (
                    account TEXT NOT NULL, address TEXT NOT NULL, attempted REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS security_login_time ON security_logins(attempted);
            """)

    def auth_version(self, username):
        # Rotating a password or session secret invalidates outstanding sessions.
        return hmac.new(bytes.fromhex(self.secret), self.users[username]["password_hash"].encode(), hashlib.sha256).hexdigest()

    def create_session(self, username):
        token = secrets.token_urlsafe(32)
        now = time.time()
        with self.connect() as db:
            db.execute("DELETE FROM security_sessions WHERE expires<=?", (now,))
            db.execute("INSERT INTO security_sessions VALUES(?,?,?,?)",
                       (hashlib.sha256(token.encode()).hexdigest(), username, now + SESSION_SECONDS, self.auth_version(username)))
        return token

    def read_session(self, token):
        if not token or not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
            return None
        with self.connect() as db:
            row = db.execute("SELECT * FROM security_sessions WHERE token_hash=? AND expires>?",
                             (hashlib.sha256(token.encode()).hexdigest(), time.time())).fetchone()
        if row and row["username"] in self.users and hmac.compare_digest(row["auth_version"], self.auth_version(row["username"])):
            return row["username"]
        return None

    def revoke(self, token):
        if token:
            with self.connect() as db:
                db.execute("DELETE FROM security_sessions WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),))

    def csrf(self, token):
        return hmac.new(bytes.fromhex(self.secret), ("csrf:" + token).encode(), hashlib.sha256).hexdigest()

    def current_user(self, request: Request):
        token = request.cookies.get(COOKIE)
        username = self.read_session(token)
        if not username:
            raise HTTPException(401, "Authentication required")
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            supplied = request.headers.get("x-csrf-token", "")
            if not re.fullmatch(r"[0-9a-f]{64}", supplied) or not hmac.compare_digest(self.csrf(token), supplied):
                raise HTTPException(403, "CSRF validation failed")
        return username

    def reserve_login(self, username, address):
        now = time.time()
        # Reserve before the expensive hash, atomically across processes. Successful
        # requests also count: the limit cannot be bypassed with parallel logins.
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM security_logins WHERE attempted<=?", (now - LOGIN_WINDOW,))
            count, oldest = db.execute("SELECT COUNT(*),MIN(attempted) FROM security_logins WHERE account=? AND address=?", (username, address)).fetchone()
            ip_count, ip_oldest = db.execute("SELECT COUNT(*),MIN(attempted) FROM security_logins WHERE address=?", (address,)).fetchone()
            if count >= 5 or ip_count >= 30:
                retry = max(1, int((oldest if count >= 5 else ip_oldest) + LOGIN_WINDOW - now) + 1)
                raise HTTPException(429, "Too many login attempts; try again later", headers={"Retry-After": str(retry)})
            db.execute("INSERT INTO security_logins VALUES(?,?,?)", (username, address, now))



class RequestGuards:
    """Request size, origin and response controls for the coursework API."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request = Request(scope)
        if request.method not in {"GET", "HEAD", "OPTIONS"} and request.url.path != "/sensor-data":
            origin = request.headers.get("origin")
            if (origin is not None and origin != str(request.base_url).rstrip("/")) or request.headers.get("sec-fetch-site") == "cross-site":
                return await JSONResponse({"detail": "Cross-origin request denied"}, status_code=403)(scope, receive, send)
        # Bound login memory use and slow uploads; never echo credentials.
        if request.method in {"POST", "PUT", "PATCH"}:
            limit = 4096 if request.url.path == "/api/login" else MAX_BODY
            async def read_body():
                body = bytearray()
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return None
                    body.extend(message.get("body", b""))
                    if len(body) > limit:
                        raise ValueError()
                    if not message.get("more_body", False):
                        return bytes(body)
            try:
                body = await asyncio.wait_for(read_body(), timeout=10)
            except ValueError:
                return await JSONResponse({"detail": "Request too large"}, status_code=413)(scope, receive, send)
            except asyncio.TimeoutError:
                return await JSONResponse({"detail": "Request timed out"}, status_code=408)(scope, receive, send)
            if body is None:
                return
            original_receive = receive
            delivered = False
            async def buffered_receive():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return await original_receive()
            receive = buffered_receive
        async def secured_send(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend([
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"cache-control", b"no-store"),
                    (b"content-security-policy", b"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"),
                ])
                message = {**message, "headers": headers}
            await send(message)
        await self.app(scope, receive, secured_send)
