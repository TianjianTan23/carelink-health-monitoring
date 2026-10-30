"""All identities, passwords, tokens and DBs here are synthetic and temporary."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from argon2 import PasswordHasher, Type
from fastapi import HTTPException
from fastapi.testclient import TestClient
from .web_auth import AuthStore, HASHER, MAX_BUCKETS, TTL, WINDOW, hash_password, token_hash, verify_password

PASSWORD = "synthetic-patient-password-only"
SALT = "ab" * 16
LEGACY = "pbkdf2_sha256$310000$"+SALT+"$"+hashlib.pbkdf2_hmac("sha256", PASSWORD.encode(), bytes.fromhex(SALT), 310000).hex()
ACCOUNTS = {"fixture_patient":{"password_hash":LEGACY,"role":"patient","mode":"basic","patient_ids":["ttj"]},
            "fixture_nurse":{"password_hash":LEGACY,"role":"clinician","mode":"pro","patient_ids":["ttj"]}}


class BootstrapTests(unittest.TestCase):
    def test_missing_private_bootstrap_has_no_public_password_fallback(self):
        from .web_auth import bootstrap_accounts
        with tempfile.TemporaryDirectory() as d:
            with patch.dict(os.environ,{"CARELINK_WEB_BOOTSTRAP_FILE":str(Path(d)/'missing.json')},clear=True):
                with self.assertRaises(RuntimeError):bootstrap_accounts({'ttj':{**ACCOUNTS['fixture_patient'],'password_hash':''}})

    def test_private_legacy_import_preserves_hash_and_rejects_unsafe_permissions(self):
        from .web_auth import bootstrap_accounts
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'bootstrap.json'
            p.write_text(json.dumps({'version':1,'users':{'ttj':{'password_hash':LEGACY}}}))
            with patch.dict(os.environ,{"CARELINK_WEB_BOOTSTRAP_FILE":str(p)},clear=True):
                p.chmod(0o600)
                result=bootstrap_accounts({'ttj':{**ACCOUNTS['fixture_patient'],'password_hash':''}})
                self.assertEqual(result['ttj']['password_hash'],LEGACY)
                p.chmod(0o644)
                with self.assertRaises(RuntimeError):bootstrap_accounts({'ttj':{**ACCOUNTS['fixture_patient'],'password_hash':''}})


class PasswordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.encoded = hash_password(PASSWORD)

    def test_argon2id_correct_wrong_and_salt(self):
        self.assertTrue(self.encoded.startswith("$argon2id$v=19$m=65536,t=3,p=1$"))
        self.assertEqual(verify_password(PASSWORD, self.encoded), (True, False))
        self.assertEqual(verify_password("wrong", self.encoded), (False, False))
        self.assertNotEqual(self.encoded, hash_password(PASSWORD))

    def test_hash_memory_concurrency_is_bounded(self):
        from .web_auth import HASH_SLOTS
        HASH_SLOTS.acquire();HASH_SLOTS.acquire()
        try:
            with self.assertRaises(HTTPException) as error:verify_password(PASSWORD,self.encoded)
            self.assertEqual(error.exception.status_code,503)
        finally:
            HASH_SLOTS.release();HASH_SLOTS.release()

    def test_invalid_and_excessive_hashes_fail_closed(self):
        for encoded in ("", "bad", "$argon2id$bad", "pbkdf2_sha256$999999999$"+SALT+"$"+"00"*32,
                        "$argon2id$v=19$m=999999999,t=3,p=1$AAAAAAAAAAAAAAAAAAAAAA$AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"):
            self.assertEqual(verify_password(PASSWORD, encoded), (False, False))

    def test_pbkdf2_migration_and_parameter_upgrade(self):
        self.assertEqual(verify_password(PASSWORD, LEGACY), (True, True))
        self.assertEqual(verify_password("wrong", LEGACY), (False, False))
        old = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1, type=Type.ID).hash(PASSWORD)
        self.assertEqual(verify_password(PASSWORD, old), (True, True))


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="carelink-auth-test-")
        self.addCleanup(self.temp.cleanup)
        self.env=patch.dict(os.environ,{k:v for k,v in os.environ.items() if not k.startswith("CARELINK_")},clear=True)
        self.env.start();self.addCleanup(self.env.stop)
        self.now=[2000000000]
        self.path=Path(self.temp.name)/"private/auth.sqlite3"
        self.store=AuthStore(self.path,clock=lambda:self.now[0])
        self.store.initialize(ACCOUNTS)

    def login(self):
        return self.store.login("fixture_patient", PASSWORD, "192.0.2.1")

    def test_gradual_migration_does_not_replace_existing_accounts(self):
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT password_hash FROM users WHERE username='fixture_patient'").fetchone()[0], LEGACY)
        self.login()
        self.store.initialize({"fixture_patient":{**ACCOUNTS['fixture_patient'],"password_hash":"bad","role":"clinician"}})
        a = self.store.account("fixture_patient")
        self.assertTrue(a['password_hash'].startswith("$argon2id$"))
        self.assertEqual(a['role'], 'patient')
        self.assertEqual(a['needs_password_rotation'], 1)

    def test_invalid_login_does_not_migrate_and_errors_are_generic(self):
        messages=[]
        for user in ("fixture_patient", "nobody"):
            with self.assertRaises(HTTPException) as error:
                self.store.login(user, "wrong", "192.0.2.1")
            messages.append((error.exception.status_code,error.exception.detail))
        self.assertEqual(messages[0],messages[1])
        self.assertEqual(self.store.account('fixture_patient')['password_hash'],LEGACY)

    def test_random_tokens_hash_only_restart_expiration_and_revocation(self):
        a,b=self.login(),self.login()
        self.assertNotEqual(a,b)
        self.assertEqual(self.store.username(a),'fixture_patient')
        with self.store.connect() as db:
            values=[tuple(r) for r in db.execute('SELECT * FROM sessions')]
            self.assertNotIn(a, str(values));self.assertNotIn(b, str(values))
            self.assertEqual(len(values),2)
        reloaded=AuthStore(self.path,clock=lambda:self.now[0])
        reloaded.initialize(ACCOUNTS)
        self.assertEqual(reloaded.username(a),'fixture_patient')
        reloaded.revoke(a)
        self.assertIsNone(AuthStore(self.path,clock=lambda:self.now[0]).username(a))
        self.now[0]+=TTL
        self.assertIsNone(reloaded.username(b))
        self.assertIsNone(reloaded.username('forged-token'))

    def test_rotation_is_atomic_old_invalid_and_absolute_expiry_preserved(self):
        old=self.login();self.now[0]+=123
        new,remaining=self.store.rotate(old)
        self.assertEqual(remaining,TTL-123)
        self.assertIsNone(self.store.username(old));self.assertEqual(self.store.username(new),'fixture_patient')
        with self.assertRaises(HTTPException):self.store.rotate(old)
        self.now[0]+=remaining
        self.assertIsNone(self.store.username(new))

    def test_password_change_revokes_all_and_does_not_reset_other_user(self):
        old=self.login();self.store.change_password('fixture_patient','new-synthetic-password-only')
        self.assertIsNone(self.store.username(old))
        self.assertEqual(self.store.account('fixture_patient')['needs_password_rotation'],0)
        self.assertEqual(self.store.account('fixture_nurse')['password_hash'],LEGACY)
        self.assertIsNotNone(self.store.login('fixture_patient','new-synthetic-password-only','192.0.2.2'))

    def test_active_and_scope_are_read_from_database(self):
        token=self.login()
        with self.store.connect() as db, db:
            db.execute("UPDATE users SET active=0 WHERE username='fixture_patient'")
        self.assertIsNone(self.store.username(token))

    def test_limit_survives_restart_and_window_expires(self):
        for _ in range(5):self.store.reserve_login('fixture_patient','192.0.2.1')
        with self.assertRaises(HTTPException) as e:
            AuthStore(self.path,clock=lambda:self.now[0]).reserve_login('fixture_patient','192.0.2.1')
        self.assertEqual(e.exception.status_code,429)
        self.now[0]+=WINDOW
        self.store.reserve_login('fixture_patient','192.0.2.1')

    def test_concurrent_limits_are_atomic(self):
        def attempt(_):
            try:self.store.reserve_login('fixture_patient','192.0.2.1');return 200
            except HTTPException as e:return e.status_code
        with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(attempt,range(12)))
        self.assertEqual(results.count(200),5);self.assertEqual(results.count(429),7)

    def test_limit_storage_is_bounded_without_active_eviction(self):
        with self.store.connect() as db, db:
            db.executemany('INSERT INTO login_limits VALUES(?,?,?)',[(str(i),self.now[0],1) for i in range(MAX_BUCKETS)])
        with self.assertRaises(HTTPException) as e:self.store.reserve_login('new','new')
        self.assertEqual(e.exception.status_code,429)
        with self.store.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM login_limits').fetchone()[0],MAX_BUCKETS)

    def test_auth_storage_cannot_alias_readings_or_nonce_ledger(self):
        for variable in ('CARELINK_DATABASE_PATH','CARELINK_DEVICE_NONCE_DB'):
            with patch.dict(os.environ,{variable:str(self.path)}):
                with self.assertRaises(RuntimeError):AuthStore(self.path)
        alias=self.path.parent/'hardlink.db'
        os.link(self.path,alias)
        with patch.dict(os.environ,{'CARELINK_DATABASE_PATH':str(alias)}):
            with self.assertRaises(RuntimeError):AuthStore(self.path)

    def test_storage_loss_fails_closed(self):
        self.path.unlink()
        with self.assertRaises(HTTPException):self.store.username('cl_s1_'+secrets.token_urlsafe(32))
        with self.assertRaises(RuntimeError):self.store.initialize(ACCOUNTS)


class WebSecurityTests(unittest.TestCase):
    def setUp(self):
        from . import app as module
        self.module=module
        self.temp=tempfile.TemporaryDirectory(prefix='carelink-web-auth-test-')
        root=Path(self.temp.name)
        from .device_auth_test_support import fixture_device_control
        self.env=patch.dict(os.environ,{**fixture_device_control(root),'CARELINK_AUTH_DATABASE_PATH':str(root/'private/auth.db'),'CARELINK_WEB_ORIGINS':'https://testserver','CARELINK_LOGIN_TEST_LIMIT':'100'})
        self.env.start()
        self.db=patch.object(module,'DATABASE_PATH',root/'readings.db');self.db.start()
        self.accounts=patch.dict(module.USERS,ACCOUNTS,clear=True);self.accounts.start()
        self.context=TestClient(module.app,base_url='https://testserver')
        self.client=self.context.__enter__()
        self.headers={'X-CareLink-CSRF':'1','Content-Type':'application/json','Origin':'https://testserver'}

    def tearDown(self):
        self.context.__exit__(None,None,None);self.accounts.stop();self.db.stop();self.env.stop();self.temp.cleanup()

    def login(self,**extra):
        return self.client.post('/api/login',json={'username':'fixture_patient','password':PASSWORD,**extra},headers=self.headers)

    def test_unauthenticated_scope_and_role_enforcement(self):
        for path in ['/api/session','/api/patients','/api/alerts','/api/patients/ttj/readings']:
            self.assertEqual(self.client.get(path).status_code,401)
        self.assertEqual(self.login().status_code,200)
        self.assertEqual(self.client.get('/api/patients/other/readings').status_code,403)
        self.assertEqual(self.client.post('/api/alerts/1/acknowledgement',json={},headers=self.headers).status_code,403)
        self.assertEqual(self.login(role='clinician',patientIds=['other']).status_code,422)
        with self.module.auth_store().connect() as db, db:
            db.execute("UPDATE users SET patient_ids='[]' WHERE username='fixture_patient'")
        self.assertEqual(self.client.get('/api/patients').status_code,403)

    def test_secure_cookie_logout_and_copied_token_cannot_be_reused(self):
        response=self.login();self.assertEqual(response.status_code,200)
        cookie=response.headers['set-cookie']
        for flag in ['Secure','HttpOnly','SameSite=lax','Path=/']:self.assertIn(flag,cookie)
        token=self.client.cookies.get('carelink_session')
        self.assertEqual(self.client.get('/api/session').status_code,200)
        self.assertEqual(self.client.post('/api/logout',json={},headers=self.headers).status_code,200)
        self.assertEqual(self.client.get('/api/session',headers={'Cookie':'carelink_session='+token}).status_code,401)

    def test_login_and_rotation_prevent_session_fixation(self):
        self.login();old=self.client.cookies.get('carelink_session')
        self.login();new=self.client.cookies.get('carelink_session')
        self.assertNotEqual(old,new)
        self.assertEqual(self.client.get('/api/session',headers={'Cookie':'carelink_session='+old}).status_code,401)
        self.assertEqual(self.client.post('/api/session/rotate',json={},headers=self.headers).status_code,200)
        self.assertEqual(self.client.get('/api/session',headers={'Cookie':'carelink_session='+new}).status_code,401)
        self.assertEqual(self.client.get('/api/session').status_code,200)

    def test_csrf_cors_https_host_and_duplicate_headers(self):
        body={'username':'fixture_patient','password':PASSWORD}
        self.assertEqual(self.client.post('/api/login',json=body).status_code,403)
        self.assertEqual(self.client.post('/api/login',json=body,headers={**self.headers,'Origin':'https://evil.invalid'}).status_code,403)
        self.assertEqual(self.client.get('/api/session',headers={'Origin':'https://evil.invalid'}).status_code,403)
        self.assertEqual(self.client.get('/api/session',headers={'Host':'evil.invalid'}).status_code,403)
        self.assertEqual(self.client.post('/api/login',json=body,headers={**self.headers,'Sec-Fetch-Site':'cross-site'}).status_code,403)
        self.assertEqual(self.client.get('/api/session',headers=[('Origin','https://testserver'),('Origin','https://testserver')]).status_code,400)
        self.assertEqual(self.client.get('http://testserver/api/session').status_code,426)
        preflight={'Origin':'https://testserver','Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'Content-Type, X-CareLink-CSRF'}
        good=self.client.options('/api/login',headers=preflight)
        self.assertEqual(good.status_code,204);self.assertEqual(good.headers['access-control-allow-origin'],'https://testserver')
        bad=self.client.options('/api/login',headers={**preflight,'Origin':'https://evil.invalid'})
        self.assertEqual(bad.status_code,403);self.assertNotIn('access-control-allow-origin',bad.headers)

    def test_login_errors_do_not_echo_passwords_and_limits_are_enforced(self):
        response=self.client.post('/api/login',json={'username':'fixture_patient','password':PASSWORD,'secret':PASSWORD},headers=self.headers)
        self.assertEqual(response.status_code,422);self.assertNotIn(PASSWORD,response.text)
        with patch.dict(os.environ,{'CARELINK_LOGIN_TEST_LIMIT':'1'}):
            statuses=[]
            for _ in range(2):
                statuses.append(self.client.post('/api/login',json={'username':'missing','password':PASSWORD},headers=self.headers).status_code)
            self.assertEqual(statuses,[401,429])

    def test_missing_origin_configuration_and_missing_auth_database_fail_closed(self):
        with patch.dict(os.environ,{'CARELINK_WEB_ORIGINS':''}):
            self.assertEqual(self.client.get('/api/session').status_code,403)
        self.login();Path(os.environ['CARELINK_AUTH_DATABASE_PATH']).unlink()
        self.assertEqual(self.client.get('/api/session').status_code,503)

    def test_referer_fallback_and_request_size_limit(self):
        h = {'X-CareLink-CSRF':'1','Content-Type':'application/json','Referer':'https://evil.invalid/login'}
        self.assertEqual(self.client.post('/api/login',json={},headers=h).status_code,403)
        h['Referer']='https://['
        self.assertEqual(self.client.post('/api/login',json={},headers=h).status_code,403)
        self.assertEqual(self.client.post('/api/login',content='x'*8193,headers=self.headers).status_code,413)
        h['Referer']='https://testserver/'
        self.assertEqual(self.client.post('/api/login',json={'username':'fixture_patient','password':PASSWORD},headers=h).status_code,200)
        self.assertEqual(self.client.post('/api/logout',json={}).status_code,403)
        self.assertEqual(self.client.get('/api/session').status_code,200)
