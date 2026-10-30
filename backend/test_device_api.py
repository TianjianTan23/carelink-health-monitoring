import importlib
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sqlite3
from contextlib import closing
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from .nonce_ledger import initialize_new_ledger, AUTHORIZATION
from .device_auth_test_support import signed_headers, write_registry, fixture_web_config


class DeviceApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="carelink-secure-api-")
        root = Path(cls.tmp.name)
        cls.registry, cls.nonces, cls.database = root/'auth/devices.json', root/'auth/nonces.sqlite3', root/'readings.db'
        write_registry(cls.registry)
        initialize_new_ledger(cls.nonces, authorization=AUTHORIZATION)
        cls.env = patch.dict(os.environ, {**fixture_web_config(root), "CARELINK_AUTH_DATABASE_PATH":str(root/"auth/web.sqlite3"), "CARELINK_WEB_ORIGINS":"https://testserver", "CARELINK_DEVICE_REGISTRY":str(cls.registry), "CARELINK_DEVICE_NONCE_DB":str(cls.nonces)})
        cls.env.start()
        cls.module = importlib.import_module('backend.app')
        cls.db_patch = patch.object(cls.module,'DATABASE_PATH',cls.database)
        cls.db_patch.start()
        cls.context = TestClient(cls.module.app,base_url='https://testserver')
        cls.client = cls.context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.context.__exit__(None,None,None)
        cls.db_patch.stop(); cls.env.stop(); cls.tmp.cleanup()

    def count(self):
        with closing(sqlite3.connect(self.database)) as db, db:
            return db.execute('SELECT count(*) FROM readings').fetchone()[0]

    def body(self):
        return json.dumps({'device_id':'esp32-test','heart_rate_bpm':76,'object_temp_c':36.7,'fall_detected':False},separators=(',',':')).encode()

    def test_authentication_is_required_before_ingestion(self):
        before=self.count()
        self.assertEqual(self.client.post('/sensor-data',content=self.body(),headers={'Content-Type':'application/json'}).status_code,401)
        self.assertEqual(self.count(),before)

    def test_valid_post_persists_and_replay_does_not(self):
        body=self.body();headers=signed_headers(body);before=self.count()
        result=self.client.post('/sensor-data',content=body,headers=headers)
        self.assertEqual(result.status_code,200)
        self.assertEqual(self.count(),before+1)
        self.assertEqual(result.json()['classification'],'normal')
        self.assertFalse(result.json()['actions']['buzzer'])
        self.assertEqual(self.client.post('/sensor-data',content=body,headers=headers).status_code,409)
        self.assertEqual(self.count(),before+1)

    def test_malformed_json_is_rejected_without_new_row(self):
        before=self.count();body=b'{broken'
        self.assertEqual(self.client.post('/sensor-data',content=body,headers=signed_headers(body)).status_code,422)
        self.assertEqual(self.count(),before)

    def test_http_even_with_valid_signature_is_rejected(self):
        body=self.body();before=self.count()
        with TestClient(self.module.app,base_url='http://testserver') as client:
            self.assertEqual(client.post('/sensor-data',content=body,headers=signed_headers(body)).status_code,426)
        self.assertEqual(self.count(),before)

    def test_duplicate_authentication_header_rejected(self):
        body=self.body();headers=list(signed_headers(body).items())
        headers.append(('X-CareLink-Nonce','f'*32))
        self.assertEqual(self.client.post('/sensor-data',content=body,headers=headers).status_code,401)

    def test_query_string_and_noncanonical_path_rejected(self):
        body=self.body();headers=signed_headers(body)
        self.assertEqual(self.client.post('/sensor-data?extra=1',content=body,headers=headers).status_code,400)
        self.assertEqual(self.client.post('/%73ensor-data',content=body,headers=headers).status_code,400)

    def test_oversized_body_rejected_before_storage(self):
        body=self.body()+b' '*32768;before=self.count()
        self.assertEqual(self.client.post('/sensor-data',content=body,headers=signed_headers(body)).status_code,413)
        self.assertEqual(self.count(),before)

    def test_missing_registry_fails_closed(self):
        body=self.body();before=self.count()
        with patch.dict(os.environ,{'CARELINK_DEVICE_REGISTRY':str(self.registry.parent/'missing.json')}):
            self.assertEqual(self.client.post('/sensor-data',content=body,headers=signed_headers(body)).status_code,503)
        self.assertEqual(self.count(),before)

    def test_optional_device_only_ingress_has_no_web_or_login_routes(self):
        ingress=importlib.import_module('backend.device_ingress')
        body=self.body();before=self.count()
        with TestClient(ingress.app,base_url='https://testserver') as client:
            self.assertEqual(client.get('/health').json()['service'],'carelink-device-ingress')
            for path in ['/','/docs','/api/session']:
                self.assertEqual(client.get(path).status_code,404)
            self.assertEqual(client.post('/api/login',json={}).status_code,404)
            self.assertEqual(client.post('/sensor-data',content=body,headers=signed_headers(body)).status_code,200)
        self.assertEqual(self.count(),before+1)

    def test_rejected_auth_does_not_refresh_a_stale_reading(self):
        body=self.body()
        response=self.client.post('/sensor-data',content=body,headers=signed_headers(body))
        self.assertEqual(response.status_code,200)
        old_time=(datetime.now(timezone.utc)-timedelta(seconds=120)).isoformat()
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute('UPDATE readings SET created_at=? WHERE id=?',(old_time,response.json()['id']))
        before=self.module._patient_payload()['reading']
        self.assertFalse(before['connected'])
        self.assertEqual(before['receivedAt'],old_time)
        bad=signed_headers(body);bad['X-CareLink-Api-Key']='x'*44
        self.assertEqual(self.client.post('/sensor-data',content=body,headers=bad).status_code,401)
        after=self.module._patient_payload()['reading']
        self.assertFalse(after['connected'])
        self.assertEqual(after['receivedAt'],old_time)
