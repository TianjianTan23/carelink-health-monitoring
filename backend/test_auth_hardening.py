from .process_test_support import checked_run
"""Phase 1 regression tests; synthetic credentials and temporary databases only."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import io
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from .web_auth import AuthStore, TTL, WINDOW, hash_password, verify_password
from .test_web_auth import ACCOUNTS, LEGACY, PASSWORD

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("auth_admin", ROOT/"scripts/manage-web-auth.py")
admin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(admin)


class HardeningStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="carelink-phase1-")
        self.addCleanup(self.temp.cleanup)
        self.env=patch.dict(os.environ,{k:v for k,v in os.environ.items() if not k.startswith("CARELINK_")},clear=True)
        self.env.start();self.addCleanup(self.env.stop)
        self.path=Path(self.temp.name)/"private/auth.db"
        self.now=[2000000000]
        self.store=AuthStore(self.path,clock=lambda:self.now[0])
        self.store.initialize(ACCOUNTS)

    def login(self):
        return self.store.login("fixture_patient", PASSWORD, "192.0.2.1")

    def test_private_files_from_creation_even_with_permissive_umask(self):
        other = AuthStore(self.path.parent/"new.db")
        old = os.umask(0)
        try:
            other.initialize(ACCOUNTS)
            with other.connect() as db, db:
                db.execute("UPDATE users SET updated_at=updated_at+1")
                for p in (other.path, other.marker, Path(str(other.path)+"-wal"), Path(str(other.path)+"-shm")):
                    if p.exists():
                        self.assertEqual(p.stat().st_mode & 0o777, 0o600)
        finally:
            os.umask(old)

    def test_unsafe_permissions_rejected_without_silent_chmod(self):
        for target, mode in ((self.path,0o644),(self.store.marker,0o644),(self.path.parent,0o755)):
            original = target.stat().st_mode & 0o777
            target.chmod(mode)
            try:
                with self.assertRaises(HTTPException) as e:
                    with self.store.connect(): pass
                self.assertEqual(e.exception.status_code,503)
                self.assertEqual(target.stat().st_mode & 0o777,mode)
            finally:
                target.chmod(original)

    def test_symlink_database_and_hardlink_database_rejected(self):
        real = self.path.with_name("real.db")
        self.path.rename(real)
        self.path.symlink_to(real)
        with self.assertRaises(HTTPException):
            with self.store.connect(): pass
        self.path.unlink()
        real.rename(self.path)
        alias = self.path.with_name("alias.db")
        os.link(self.path,alias)
        with self.assertRaises(HTTPException):
            with self.store.connect(): pass
        alias.unlink()

    def test_sidecar_symlink_rejected_before_sqlite_access(self):
        target = self.path.parent/"unrelated.txt"
        target.write_text("unrelated synthetic data")
        before = target.read_bytes()
        wal = Path(str(self.path)+"-wal")
        wal.symlink_to(target)
        try:
            with self.assertRaises(HTTPException):
                with self.store.connect(): pass
            self.assertTrue(target.read_bytes()==before)
        finally:
            wal.unlink()

    def test_missing_marker_never_reseeds_existing_database(self):
        self.store.marker.unlink()
        before = self.path.read_bytes()
        with self.assertRaises(RuntimeError):self.store.initialize(ACCOUNTS)
        self.assertTrue(before==self.path.read_bytes())
        self.assertFalse(self.store.marker.exists())

    def test_deleted_account_not_restored_from_stale_bootstrap(self):
        with self.store.connect() as db, db:
            db.execute("DELETE FROM users WHERE username='fixture_nurse'")
        self.store.initialize(ACCOUNTS)
        with self.assertRaises(HTTPException):self.store.account("fixture_nurse")

    def test_schema_damage_is_not_silently_repaired(self):
        with self.store.connect() as db:
            db.executescript("DROP TABLE sessions; CREATE TABLE sessions(token_hash TEXT)")
        with self.assertRaises(HTTPException):self.store.initialize(ACCOUNTS)
        with self.store.connect() as db:
            self.assertEqual(len(list(db.execute("PRAGMA table_info(sessions)"))),1)

    def test_sqlite_uri_reserved_characters_are_encoded(self):
        other = AuthStore(self.path.parent/"uri?#.db")
        other.initialize(ACCOUNTS)
        self.assertEqual(other.account("fixture_patient")["role"],"patient")
        self.assertFalse((self.path.parent/"uri").exists())

    def test_short_legacy_success_migrates_without_claiming_rotation(self):
        password = "short"
        legacy = "pbkdf2_sha256$310000$"+"cd"*16+"$"+hashlib.pbkdf2_hmac("sha256",password.encode(),bytes.fromhex("cd"*16),310000).hex()
        with self.store.connect() as db, db:
            db.execute("UPDATE users SET password_hash=? WHERE username='fixture_patient'",(legacy,))
        self.store.login("fixture_patient",password,"192.0.2.1")
        account = self.store.account("fixture_patient")
        self.assertTrue(account["password_hash"].startswith("$argon2id$"))
        self.assertTrue(verify_password(password,account["password_hash"])[0])
        self.assertEqual(account["needs_password_rotation"],1)

    def test_invalid_password_change_does_not_revoke_or_overwrite(self):
        token = self.login()
        before = self.store.account("fixture_patient")["password_hash"]
        for password in ("tiny", "界"*400):
            with self.assertRaises(ValueError):self.store.change_password("fixture_patient",password)
        self.assertTrue(self.store.account("fixture_patient")["password_hash"]==before)
        self.assertEqual(self.store.username(token),"fixture_patient")
        with self.assertRaises(ValueError):self.store.replace_password_hash("fixture_patient",LEGACY)

    def test_plaintext_or_invalid_bootstrap_never_stored(self):
        for i, encoded in enumerate((PASSWORD,"$argon2id$invalid","pbkdf2_sha256$invalid")):
            target=AuthStore(self.path.parent/f"invalid-{i}.db")
            with self.assertRaises(RuntimeError):
                target.initialize({"fixture_patient":{**ACCOUNTS["fixture_patient"],"password_hash":encoded}})
            self.assertFalse(target.path.exists())
            self.assertFalse(target.marker.exists())

    def test_private_bootstrap_symlink_and_hardlink_rejected(self):
        import json
        from .web_auth import bootstrap_accounts
        source=self.path.parent/"bootstrap.json"
        source.write_text(json.dumps({"version":1,"users":{"ttj":{"password_hash":LEGACY}}}));source.chmod(0o600)
        link=self.path.parent/"bootstrap-link.json";link.symlink_to(source)
        definition={"ttj":{**ACCOUNTS["fixture_patient"],"password_hash":""}}
        with patch.dict(os.environ,{"CARELINK_WEB_BOOTSTRAP_FILE":str(link)},clear=True):
            with self.assertRaises(RuntimeError):bootstrap_accounts(definition)
        link.unlink();os.link(source,link)
        with patch.dict(os.environ,{"CARELINK_WEB_BOOTSTRAP_FILE":str(source)},clear=True):
            with self.assertRaises(RuntimeError):bootstrap_accounts(definition)

    def test_login_disabled_and_unknown_have_same_failure(self):
        with self.store.connect() as db, db:
            db.execute("UPDATE users SET active=0 WHERE username='fixture_patient'")
        outcomes = []
        for username in ("fixture_patient","absent"):
            with self.assertRaises(HTTPException) as e:self.store.login(username,PASSWORD,"192.0.2.1")
            outcomes.append((e.exception.status_code,e.exception.detail))
        self.assertEqual(outcomes[0],outcomes[1])

    def test_retry_after_is_remaining_window_not_fixed_900(self):
        for _ in range(5):self.store.reserve_login("fixture_patient","192.0.2.1")
        self.now[0]+=123
        with self.assertRaises(HTTPException) as e:self.store.reserve_login("fixture_patient","192.0.2.1")
        self.assertEqual(e.exception.headers["Retry-After"],str(WINDOW-123))
        self.now[0]+=WINDOW-123
        self.store.reserve_login("fixture_patient","192.0.2.1")

    def test_multiple_blocking_buckets_wait_for_longest(self):
        for _ in range(5):self.store.reserve_login("fixture_patient","192.0.2.1")
        self.now[0]+=100
        for _ in range(5):self.store.reserve_login("fixture_patient","192.0.2.2")
        with self.assertRaises(HTTPException) as e:self.store.reserve_login("fixture_patient","192.0.2.2")
        self.assertEqual(e.exception.headers["Retry-After"],str(WINDOW))

    def test_only_one_concurrent_rotation_succeeds(self):
        token = self.login()
        def rotate(_):
            try:return self.store.rotate(token)[0]
            except HTTPException as e:return e.status_code
        with ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(rotate,range(6)))
        self.assertEqual(sum(isinstance(r,str) for r in results),1)
        self.assertEqual(results.count(401),5)
        self.assertIsNone(self.store.username(token))


class OperatorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="carelink-operator-")
        self.path = Path(self.temp.name)/"private/offline.db"

    def tearDown(self):self.temp.cleanup()

    def test_prepare_all_accounts_argon_scopes_preserved_no_legacy_import(self):
        values = iter([PASSWORD,PASSWORD,PASSWORD,PASSWORD])
        admin.prepare(self.path,ACCOUNTS,prompt=lambda _:next(values))
        target = AuthStore(self.path)
        for username, expected in ACCOUNTS.items():
            account = target.account(username)
            self.assertTrue(account["password_hash"].startswith("$argon2id$"))
            self.assertTrue(account["password_hash"]!=LEGACY)
            self.assertEqual(account["role"],expected["role"])
            self.assertEqual(account["patient_ids"],expected["patient_ids"])
            self.assertEqual(account["needs_password_rotation"],0)
        self.assertTrue(target.account("fixture_patient")["password_hash"]!=target.account("fixture_nurse")["password_hash"])

    def test_prepare_mismatch_or_policy_failure_has_no_database_side_effect(self):
        for inputs in ([PASSWORD,PASSWORD,"tiny","tiny"],[PASSWORD,PASSWORD,PASSWORD,"different"]):
            values = iter(inputs)
            with self.assertRaises(ValueError):admin.prepare(self.path,ACCOUNTS,prompt=lambda _:next(values))
            self.assertFalse(self.path.parent.exists())

    def test_prepare_refuses_existing_target_without_prompt_or_write(self):
        target = AuthStore(self.path);target.initialize(ACCOUNTS)
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):admin.prepare(self.path,ACCOUNTS,prompt=lambda _:self.fail("Unexpected password prompt"))
        self.assertTrue(before==self.path.read_bytes())

    def test_rotate_only_target_account_and_revokes_sessions(self):
        target = AuthStore(self.path);target.initialize(ACCOUNTS)
        token = target.login("fixture_patient",PASSWORD,"192.0.2.1")
        values = iter([PASSWORD,PASSWORD])
        admin.rotate(self.path,"fixture_patient",prompt=lambda _:next(values))
        self.assertIsNone(target.username(token))
        self.assertEqual(target.account("fixture_patient")["needs_password_rotation"],0)
        self.assertTrue(target.account("fixture_nurse")["password_hash"]==LEGACY)

    def test_operator_requires_terminal_and_explicit_absolute_target(self):
        for args in (["prepare"],["prepare","--database","relative.db"],["prepare","--database",str(self.path)]):
            result = checked_run([sys.executable,str(ROOT/"scripts/manage-web-auth.py"),*args],input="",text=True,capture_output=True)
            self.assertNotEqual(result.returncode,0)
            self.assertFalse(self.path.parent.exists())
            self.assertFalse("$argon2" in result.stdout+result.stderr)

    def test_no_echo_fallback_if_getpass_cannot_hide_input(self):
        import warnings
        from getpass import GetPassWarning
        def cannot_hide(_):warnings.warn("cannot hide input",GetPassWarning)
        with self.assertRaises(GetPassWarning):admin.prepare(self.path,ACCOUNTS,prompt=cannot_hide)
        self.assertFalse(self.path.parent.exists())


class MiddlewareRegressionTests(unittest.TestCase):
    def setUp(self):
        from . import app as module
        self.module=module
        self.temp=tempfile.TemporaryDirectory(prefix="carelink-phase1-api-")
        root=Path(self.temp.name)
        from .device_auth_test_support import fixture_device_control
        self.env=patch.dict(os.environ,{**fixture_device_control(root),"CARELINK_AUTH_DATABASE_PATH":str(root/"private/auth.db"),"CARELINK_WEB_ORIGINS":"https://testserver","CARELINK_LOGIN_TEST_LIMIT":"100"})
        self.env.start()
        self.readings=patch.object(module,"DATABASE_PATH",root/"readings.db");self.readings.start()
        self.accounts=patch.dict(module.USERS,ACCOUNTS,clear=True);self.accounts.start()
        self.context=TestClient(module.app,base_url="https://testserver")
        self.client=self.context.__enter__()
        self.headers={"X-CareLink-CSRF":"1","Content-Type":"application/json","Origin":"https://testserver"}

    def tearDown(self):
        self.context.__exit__(None,None,None);self.accounts.stop();self.readings.stop();self.env.stop();self.temp.cleanup()

    def login(self):return self.client.post("/api/login",headers=self.headers,json={"username":"fixture_patient","password":PASSWORD})

    def test_expired_and_revoked_session_rejected_by_actual_data_route(self):
        self.assertEqual(self.login().status_code,200)
        self.assertEqual(self.client.get("/api/patients/ttj/readings").status_code,200)
        with self.module.auth_store().connect() as db, db:db.execute("UPDATE sessions SET expires_at=1")
        self.assertEqual(self.client.get("/api/patients/ttj/readings").status_code,401)
        self.assertEqual(self.login().status_code,200)
        self.assertEqual(self.client.post("/api/logout",json={},headers=self.headers).status_code,200)
        self.assertEqual(self.client.get("/api/patients/ttj/readings").status_code,401)

    def test_clinician_still_cannot_escape_patient_scope(self):
        response=self.client.post("/api/login",headers=self.headers,json={"username":"fixture_nurse","password":PASSWORD})
        self.assertEqual(response.status_code,200)
        self.assertEqual(self.client.get("/api/patients/not-authorized/readings").status_code,403)
        with self.module.auth_store().connect() as db, db:db.execute("UPDATE users SET active=0 WHERE username='fixture_nurse'")
        self.assertEqual(self.client.get("/api/session").status_code,401)
        self.assertEqual(self.client.post("/api/session/rotate",headers=self.headers,json={}).status_code,401)

    def test_security_denials_are_not_cacheable_and_do_not_reflect_origin(self):
        for path, headers in (("/api/session",{"Origin":"https://untrusted.invalid"}),("/api/session",{"Host":"untrusted.invalid"})):
            response=self.client.get(path,headers=headers)
            self.assertEqual(response.status_code,403)
            self.assertEqual(response.headers.get("cache-control"),"no-store")
            self.assertNotIn("access-control-allow-origin",response.headers)
        response=self.client.post("/api/logout",json={})
        self.assertEqual(response.status_code,403)
        self.assertEqual(response.headers.get("cache-control"),"no-store")

    def test_malformed_origin_config_is_not_trusted(self):
        from .web_security import allowed_origins
        for origin in ("https://testserver:bad","https://testserver:99999","https://testserver:0","https://user@testserver","https://testserver/path","http://testserver","https://testserver%2f.evil","https://testserver\\evil"):
            with patch.dict(os.environ,{"CARELINK_WEB_ORIGINS":origin}):self.assertEqual(allowed_origins(),set())

    def test_duplicate_preflight_security_headers_rejected(self):
        response=self.client.options("/api/login",headers=[("Origin","https://testserver"),("Access-Control-Request-Method","POST"),("Access-Control-Request-Method","GET")])
        self.assertEqual(response.status_code,400)
        self.assertEqual(response.headers.get("cache-control"),"no-store")

    def test_spoofed_forwarded_for_does_not_bypass_client_limit(self):
        with patch.dict(os.environ,{"CARELINK_LOGIN_TEST_LIMIT":"1"}):
            for i, expected in enumerate((401,429)):
                response=self.client.post("/api/login",json={"username":"absent","password":PASSWORD},headers={**self.headers,"X-Forwarded-For":f"192.0.2.{i}"})
                self.assertEqual(response.status_code,expected)

    def test_auth_responses_and_captured_logs_exclude_secret_values(self):
        stream=io.StringIO()
        import logging
        handler=logging.StreamHandler(stream);logger=logging.getLogger();old_level=logger.level
        logger.setLevel(logging.INFO);logger.addHandler(handler)
        try:
            self.assertEqual(self.login().status_code,200)
            token=self.client.cookies.get("carelink_session")
            result=self.client.get("/api/session")
            account=self.module.auth_store().account("fixture_patient")
            self.assertEqual(self.client.post("/api/logout",headers=self.headers,json={}).status_code,200)
            text=stream.getvalue()+result.text
            self.assertTrue("HTTP Request" in stream.getvalue())
            for secret in (PASSWORD,token,account["password_hash"]):self.assertFalse(secret in text)
        finally:logger.removeHandler(handler);logger.setLevel(old_level)


if __name__ == "__main__":unittest.main()
