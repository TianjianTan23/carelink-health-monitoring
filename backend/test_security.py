import hashlib
import json
from pathlib import Path
import secrets
import tempfile
import time
import unittest
from fastapi.testclient import TestClient
from .test_support import PASSWORDS
from . import app as api
from .security import COOKIE, HASHER, verify_password


class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous = api.DATABASE_PATH
        api.DATABASE_PATH = Path(self.temp.name) / "test.db"
        self.client = TestClient(api.app, base_url="http://testserver")
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        api.DATABASE_PATH = self.previous
        self.temp.cleanup()

    def login(self, username="ttj"):
        r = self.client.post("/api/login", json={"username": username, "password": PASSWORDS[username]})
        self.assertEqual(r.status_code, 200)
        self.client.headers["X-CSRF-Token"] = r.json()["csrfToken"]
        return r


    def test_argon2id_salted(self):
        value = secrets.token_urlsafe(24)
        first, second = HASHER.hash(value), HASHER.hash(value)
        self.assertTrue(first.startswith("$argon2id$"))
        self.assertNotEqual(first, second)
        self.assertTrue(verify_password(value, first))
        self.assertFalse(verify_password(secrets.token_urlsafe(24), first))

    def test_configuration_validation_cannot_be_disabled_by_optimization(self):
        import subprocess
        import sys
        code = '''
from argon2 import PasswordHasher, Type
import secrets
from backend.security import Security
checker = Security(None, {"ttj": {"password_hash": PasswordHasher(type=Type.I).hash(secrets.token_urlsafe(32))}})
try:
    checker.validate_configuration()
except RuntimeError:
    raise SystemExit(0)
raise SystemExit(1)
'''
        result = subprocess.run([sys.executable, "-O", "-c", code], capture_output=True)
        self.assertEqual(result.returncode, 0, "Invalid Argon2 type must be rejected even under python -O")

    def test_wrong_password_and_unknown_account_are_generic(self):
        results = [self.client.post("/api/login", json={"username": u, "password": secrets.token_urlsafe(24)}) for u in ("ttj", "unknown")]
        self.assertEqual([r.status_code for r in results], [401, 401])
        self.assertEqual(results[0].json(), results[1].json())

    def test_validation_never_echoes_password(self):
        value = secrets.token_urlsafe(800)
        r = self.client.post("/api/login", json={"username": "ttj", "password": value})
        self.assertEqual(r.status_code, 422)
        self.assertNotIn(value, r.text)

    def test_http_cookie_random_opaque_and_hashed_at_rest(self):
        r = self.login()
        cookie = r.headers.get_list("set-cookie")[0]
        for flag in ("HttpOnly", "SameSite=strict", "Path=/"):
            self.assertIn(flag, cookie)
        self.assertNotIn("Secure", cookie)
        token = self.client.cookies.get(COOKIE)
        self.assertEqual(len(token), 43)
        with api.connect() as db:
            row = db.execute("SELECT * FROM security_sessions").fetchone()
            self.assertEqual(row["token_hash"], hashlib.sha256(token.encode()).hexdigest())
        self.assertNotIn(token.encode(), api.DATABASE_PATH.read_bytes())

    def test_unauthorized_scope_and_role(self):
        self.assertEqual(self.client.get("/api/patients").status_code, 401)
        self.login()
        self.assertEqual(self.client.get("/api/patients/other").status_code, 403)
        self.assertEqual(self.client.post("/api/alerts/alert-1/acknowledgement").status_code, 403)

    def test_csrf_and_cross_origin_login(self):
        self.assertEqual(self.client.post("/api/login", headers={"Origin": "https://evil.example"}, json={"username": "ttj", "password": PASSWORDS["ttj"]}).status_code, 403)
        self.login()
        self.assertEqual(self.client.post("/api/logout", headers={"X-CSRF-Token": "wrong"}).status_code, 403)
        self.assertEqual(self.client.post("/api/logout", headers={"Origin": "https://evil.example"}).status_code, 403)
        self.assertEqual(self.client.get("/api/session").status_code, 200)

    def test_logout_revokes_stolen_copy(self):
        self.login()
        token = self.client.cookies.get(COOKIE)
        self.assertEqual(self.client.post("/api/logout").status_code, 200)
        self.client.cookies.set(COOKIE, token)
        self.assertEqual(self.client.get("/api/session").status_code, 401)

    def test_expiry_password_rotation_and_session_rotation(self):
        self.login()
        old = self.client.cookies.get(COOKIE)
        self.login()
        self.assertIsNone(api.security.read_session(old))
        with api.connect() as db:
            db.execute("UPDATE security_sessions SET expires=?", (time.time() - 1,))
        self.assertEqual(self.client.get("/api/session").status_code, 401)
        self.login()
        old_hash = api.USERS["ttj"]["password_hash"]
        try:
            api.USERS["ttj"]["password_hash"] = HASHER.hash(secrets.token_urlsafe(32))
            self.assertEqual(self.client.get("/api/session").status_code, 401)
        finally:
            api.USERS["ttj"]["password_hash"] = old_hash

    def test_rate_limit_and_expiry(self):
        payload = {"username": "ttj", "password": secrets.token_urlsafe(24)}
        for _ in range(5):
            self.assertEqual(self.client.post("/api/login", json=payload).status_code, 401)
        r = self.client.post("/api/login", json=payload)
        self.assertEqual(r.status_code, 429)
        self.assertGreater(int(r.headers["Retry-After"]), 0)
        with api.connect() as db:
            db.execute("UPDATE security_logins SET attempted=?", (time.time() - 901,))
        self.login()


    def test_unsigned_sensor_post_works_over_http(self):
        response = self.client.post("/sensor-data", json={"device_id":"http-test", "heart_rate_bpm":75, "object_temp_c":36.6, "fall_detected":False})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["label"], "normal")
        self.assertNotIn("strict-transport-security", response.headers)

    def test_oversized_sensor_request_rejected(self):
        self.assertEqual(self.client.post("/sensor-data", content=b" "*(128*1024+1), headers={"Content-Type":"application/json"}).status_code, 413)

    def test_security_headers(self):
        r = self.client.get("/api/session")
        self.assertNotIn("strict-transport-security", r.headers)
        self.assertEqual(r.headers["cache-control"], "no-store")


if __name__ == "__main__":
    unittest.main()
