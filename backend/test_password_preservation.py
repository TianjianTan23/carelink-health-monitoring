"""Preserve-password migration policy: synthetic accounts/temporary DBs only."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import os
import tempfile
import threading
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from . import web_auth
from .test_web_auth import ACCOUNTS, LEGACY, PASSWORD


class PasswordPreservationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="carelink-preserve-password-")
        self.addCleanup(self.temp.cleanup)
        env={k:v for k,v in os.environ.items() if not k.startswith("CARELINK_")}
        env['CARELINK_LOGIN_TEST_LIMIT']='100'
        self.env=patch.dict(os.environ,env,clear=True)
        self.env.start();self.addCleanup(self.env.stop)
        self.path=Path(self.temp.name)/"private/accounts.db"
        self.accounts={"ttj":dict(ACCOUNTS["fixture_patient"]),"wyn":dict(ACCOUNTS["fixture_nurse"])}
        self.store=web_auth.AuthStore(self.path)
        self.store.initialize(self.accounts)

    def assert_no_sessions(self):
        with self.store.connect() as db:self.assertEqual(db.execute("SELECT count(*) FROM sessions").fetchone()[0],0)

    def test_failure_preserves_legacy_then_original_password_migrates_and_logs_in_again(self):
        for username in ("ttj","wyn"):
            with self.assertRaises(HTTPException) as error:
                self.store.login(username,"incorrect-fixture", "192.0.2.1")
            self.assertEqual(error.exception.status_code,401)
            self.assertTrue(self.store.account(username)["password_hash"]==LEGACY)
        self.assert_no_sessions()
        for username in ("ttj","wyn"):
            token=self.store.login(username,PASSWORD,"192.0.2.1")
            account=self.store.account(username)
            self.assertTrue(account["password_hash"].startswith("$argon2id$"))
            self.assertEqual(account["needs_password_rotation"],1)  # Non-blocking legacy metadata.
            again=self.store.login(username,PASSWORD,"192.0.2.1")
            self.assertTrue(self.store.account(username)["password_hash"]==account["password_hash"])
            self.assertEqual(self.store.username(token),username)
            self.assertEqual(self.store.username(again),username)
            self.assertEqual(account["role"],self.accounts[username]["role"])
            self.assertEqual(account["patient_ids"],self.accounts[username]["patient_ids"])

    def test_two_concurrent_legacy_logins_reverify_winning_hash(self):
        barrier=threading.Barrier(2)
        original_migrate=web_auth.hash_password_for_migration
        original_verify=web_auth.verify_password
        generated=[];checked=[];lock=threading.Lock()
        def migrate(password):
            encoded=original_migrate(password)
            with lock:generated.append(encoded)
            barrier.wait(timeout=10)
            return encoded
        def verify(password,encoded):
            with lock:checked.append(encoded)
            return original_verify(password,encoded)
        with patch.object(web_auth,"hash_password_for_migration",side_effect=migrate),patch.object(web_auth,"verify_password",side_effect=verify):
            with ThreadPoolExecutor(max_workers=2) as pool:
                tokens=list(pool.map(lambda _:self.store.login("ttj",PASSWORD,"192.0.2.1"),range(2)))
        winner=self.store.account("ttj")["password_hash"]
        self.assertEqual(len(generated),2)
        self.assertTrue(generated[0]!=generated[1])
        self.assertTrue(winner in generated)
        self.assertEqual(sum(value==LEGACY for value in checked),2)
        self.assertEqual(sum(value==winner for value in checked),1)
        for token in tokens:self.assertEqual(self.store.username(token),"ttj")
        self.store.login("ttj",PASSWORD,"192.0.2.1")
        self.assertTrue(self.store.account("ttj")["password_hash"]==winner)

    def test_concurrent_credential_update_is_not_overwritten_by_stale_migration(self):
        # A competing update uses the SAME original password with a fresh salt.
        # No password reset is needed to test stale-writer protection.
        winner=web_auth.hash_password_for_migration(PASSWORD)
        original=web_auth.hash_password_for_migration
        def migrate(password):
            stale=original(password)
            with self.store.connect() as db,db:
                db.execute("UPDATE users SET password_hash=? WHERE username='ttj'",(winner,))
            return stale
        with patch.object(web_auth,"hash_password_for_migration",side_effect=migrate):
            token=self.store.login("ttj",PASSWORD,"192.0.2.1")
        self.assertTrue(self.store.account("ttj")["password_hash"]==winner)
        self.assertEqual(self.store.username(token),"ttj")

    def test_concurrent_disable_does_not_migrate_or_create_session(self):
        original=web_auth.hash_password_for_migration
        def migrate(password):
            candidate=original(password)
            with self.store.connect() as db,db:db.execute("UPDATE users SET active=0 WHERE username='ttj'")
            return candidate
        with patch.object(web_auth,"hash_password_for_migration",side_effect=migrate):
            with self.assertRaises(HTTPException) as error:self.store.login("ttj",PASSWORD,"192.0.2.1")
        self.assertEqual(error.exception.status_code,401)
        self.assert_no_sessions()
        with self.store.connect() as db:
            self.assertTrue(db.execute("SELECT password_hash FROM users WHERE username='ttj'").fetchone()[0]==LEGACY)

    def test_incompatible_existing_hash_fails_closed_without_reset_or_session(self):
        for encoded in ("unsupported-fixture-format","pbkdf2_sha256$invalid","$argon2id$invalid"):
            with self.store.connect() as db,db:db.execute("UPDATE users SET password_hash=? WHERE username='ttj'",(encoded,))
            with self.assertRaises(HTTPException) as error:self.store.login("ttj",PASSWORD,"192.0.2.1")
            self.assertEqual(error.exception.status_code,401)
            self.assertTrue(self.store.account("ttj")["password_hash"]==encoded)
            self.assert_no_sessions()

    def test_actual_login_routes_preserve_ttjs_and_wyns_password_without_reset_gate(self):
        from . import app as module
        root=Path(self.temp.name)
        from .device_auth_test_support import fixture_device_control
        env={**fixture_device_control(root),"CARELINK_AUTH_DATABASE_PATH":str(self.path),"CARELINK_WEB_ORIGINS":"https://testserver"}
        headers={"Origin":"https://testserver","X-CareLink-CSRF":"1"}
        with patch.dict(os.environ,env),patch.object(module,"DATABASE_PATH",root/"readings.db"),patch.dict(module.USERS,self.accounts,clear=True):
            with TestClient(module.app,base_url="https://testserver") as client:
                for username in ("ttj","wyn"):
                    for _ in range(2):
                        response=client.post("/api/login",headers=headers,json={"username":username,"password":PASSWORD})
                        self.assertEqual(response.status_code,200)
                        self.assertEqual(response.json()["role"],self.accounts[username]["role"])
                        self.assertFalse(PASSWORD in response.text)
                        self.assertEqual(client.get("/api/session").status_code,200)
                        self.assertEqual(client.get("/api/patients/ttj/readings").status_code,200)
                        self.assertEqual(client.get("/api/patients/outside-scope/readings").status_code,403)
                        self.assertEqual(client.post("/api/logout",headers=headers,json={}).status_code,200)
                    self.assertEqual(self.store.account(username)["needs_password_rotation"],1)


if __name__=="__main__":unittest.main()
