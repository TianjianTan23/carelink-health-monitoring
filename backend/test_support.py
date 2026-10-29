"""Ephemeral test credentials: generated in memory, never printed or committed."""
import json
import os
import secrets
from argon2 import PasswordHasher, Type
from fastapi.testclient import TestClient

PASSWORDS = {name: secrets.token_urlsafe(24) for name in ("ttj", "wyn")}
hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2, type=Type.ID)
os.environ["CARELINK_PATIENT_PASSWORD_HASH"] = hasher.hash(PASSWORDS["ttj"])
os.environ["CARELINK_NURSE_PASSWORD_HASH"] = hasher.hash(PASSWORDS["wyn"])
os.environ["CARELINK_SESSION_SECRET"] = secrets.token_hex(32)


class AccountClient(TestClient):
    """Monitoring tests use real HTTP sessions with CSRF forwarding."""
    def __init__(self, app, **kwargs):
        super().__init__(app, base_url="http://testserver", **kwargs)

    def post(self, url, **kwargs):
        response = super().post(url, **kwargs)
        if url == "/api/login" and response.status_code == 200:
            self.headers["X-CSRF-Token"] = response.json()["csrfToken"]
        return response
