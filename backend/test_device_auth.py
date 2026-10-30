from concurrent.futures import ThreadPoolExecutor
import hashlib
import hmac
import json
from pathlib import Path
import sqlite3
from contextlib import closing
import tempfile
import time
import unittest

from .nonce_ledger import initialize_new_ledger, AUTHORIZATION
from .device_auth import DeviceAuthenticator, DeviceAuthError, canonical_request
from .device_auth_test_support import fixture_credentials, signed_headers, write_registry


class DeviceAuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="carelink-device-auth-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.registry, self.nonces = self.root / "devices.json", self.root / "nonces.sqlite3"
        write_registry(self.registry)
        initialize_new_ledger(self.nonces, authorization=AUTHORIZATION)
        self.auth = DeviceAuthenticator(self.registry, self.nonces)
        self.body = b'{"device_id":"esp32-test","heart_rate_bpm":72,"object_temp_c":36.5,"fall_detected":false}'

    def headers(self, **kwargs):
        return {k.lower():v for k,v in signed_headers(self.body, **kwargs).items()}

    def accept(self, headers=None, body=None, auth=None):
        return (auth or self.auth).authenticate_payload("POST",b"/sensor-data",b"",headers or self.headers(), self.body if body is None else body)

    def rejected(self, status, function):
        with self.assertRaises(DeviceAuthError) as error:
            function()
        self.assertEqual(error.exception.status, status)

    def test_canonical_vector_is_exact_and_has_no_trailing_newline(self):
        body=b'{"device_id":"esp32-test","heart_rate_bpm":72}'
        expected=b'CARELINK-HMAC-SHA256-V1\nPOST\n/sensor-data\nesp32-test\n1793100000\n000102030405060708090a0b0c0d0e0f\n'+hashlib.sha256(body).hexdigest().encode()
        self.assertEqual(canonical_request("POST","/sensor-data","esp32-test","1793100000","000102030405060708090a0b0c0d0e0f",body),expected)

    def test_good_request_and_independent_devices(self):
        self.assertEqual(self.accept()["device_id"], "esp32-test")
        other=self.body.replace(b'esp32-test',b'quality-test')
        headers={k.lower():v for k,v in signed_headers(other,"quality-test").items()}
        self.assertEqual(self.accept(headers,other)["device_id"],"quality-test")
        self.assertNotEqual(fixture_credentials("esp32-test"),fixture_credentials("quality-test"))

    def test_wrong_api_and_wrong_hmac(self):
        for key,value in [("x-carelink-api-key","x"*44),("x-carelink-signature","0"*64)]:
            headers=self.headers();headers[key]=value
            self.rejected(401,lambda:self.accept(headers))

    def test_expired_and_future_timestamps(self):
        for delta in (-120,120,-3600,3600):
            self.rejected(401,lambda:self.accept(self.headers(timestamp=int(time.time())+delta)))

    def test_exact_window_boundaries(self):
        now=1793100000
        for delta in (-60,60):
            self.auth.verify("POST",b"/sensor-data",b"",self.headers(timestamp=now+delta),self.body,now=now)
        for delta in (-61,61):
            self.rejected(401,lambda:self.auth.verify("POST",b"/sensor-data",b"",self.headers(timestamp=now+delta),self.body,now=now))

    def test_timestamp_and_nonce_encoding_is_strict(self):
        for field,value in [("x-carelink-timestamp","01793100000"),("x-carelink-timestamp","1e9"),("x-carelink-nonce","0"*31),("x-carelink-nonce","A"*32)]:
            headers=self.headers();headers[field]=value
            self.rejected(401,lambda:self.accept(headers))

    def test_body_method_path_and_device_are_bound(self):
        headers=self.headers()
        self.rejected(401,lambda:self.accept(headers,self.body+b' '))
        self.rejected(400,lambda:self.auth.verify("PUT",b"/sensor-data",b"",headers,self.body))
        self.rejected(400,lambda:self.auth.verify("POST",b"/%73ensor-data",b"",headers,self.body))
        self.rejected(400,lambda:self.auth.verify("POST",b"/sensor-data",b"x=1",headers,self.body))
        headers['x-carelink-device-id']='quality-test'
        self.rejected(401,lambda:self.accept(headers))

    def test_duplicate_nonce_persists_after_authenticator_restart(self):
        headers=self.headers();self.accept(headers)
        self.rejected(409,lambda:self.accept(headers))
        restarted=DeviceAuthenticator(self.registry,self.nonces)
        self.rejected(409,lambda:self.accept(headers,auth=restarted))
        refreshed=self.headers(nonce=headers['x-carelink-nonce'])
        self.rejected(409,lambda:self.accept(refreshed,auth=restarted))

    def test_atomic_concurrent_replay_has_one_winner(self):
        headers=self.headers()
        def send(_):
            try:self.accept(headers);return 200
            except DeviceAuthError as error:return error.status
        with ThreadPoolExecutor(max_workers=8) as pool:
            statuses=list(pool.map(send,range(16)))
        self.assertEqual(statuses.count(200),1)
        self.assertEqual(statuses.count(409),15)

    def test_invalid_payload_and_duplicate_keys_are_not_stored_or_reserved(self):
        for body in [b'[]',b'{broken',b'{"device_id":"esp32-test"}',b'{"device_id":"esp32-test","heart_rate_bpm":"72"}',b'{"device_id":"esp32-test","heart_rate_bpm":NaN}',b'{"device_id":"esp32-test","heart_rate_bpm":72,"heart_rate_bpm":73}',b'{"device_id":"esp32-test","fall_detected":1}']:
            headers={k.lower():v for k,v in signed_headers(body).items()}
            self.rejected(422,lambda:self.accept(headers,body))
        with closing(sqlite3.connect(self.nonces)) as db, db:
            self.assertEqual(db.execute('SELECT count(*) FROM device_nonces').fetchone()[0],0)

    def test_valid_signature_cannot_impersonate_body_device(self):
        body=self.body.replace(b'esp32-test',b'quality-test')
        headers={k.lower():v for k,v in signed_headers(body).items()}
        self.rejected(403,lambda:self.accept(headers,body))

    def test_disabled_missing_or_unsafe_registry_fails_closed(self):
        data=json.loads(self.registry.read_text());data['devices']['esp32-test']['enabled']=False;self.registry.write_text(json.dumps(data))
        disabled=DeviceAuthenticator(self.registry,self.nonces)
        self.rejected(401,lambda:self.accept(auth=disabled))
        self.rejected(503,lambda:DeviceAuthenticator(self.root/'missing.json',self.nonces))
        self.registry.chmod(0o644)
        self.rejected(503,lambda:DeviceAuthenticator(self.registry,self.nonces))

    def test_shared_credentials_between_devices_are_rejected(self):
        data=json.loads(self.registry.read_text())
        data['devices']['quality-test']['hmac_key_hex']=data['devices']['esp32-test']['hmac_key_hex']
        self.registry.write_text(json.dumps(data))
        self.rejected(503,lambda:DeviceAuthenticator(self.registry,self.nonces))

    def test_corrupt_nonce_database_fails_closed(self):
        self.nonces.write_bytes(b'not a sqlite database')
        self.rejected(503,lambda:self.accept())

    def test_lost_or_truncated_ledger_is_not_silently_reset_after_restart(self):
        self.accept()
        self.nonces.unlink()
        self.rejected(503,lambda:DeviceAuthenticator(self.registry,self.nonces))
        self.nonces.write_bytes(b'')
        self.rejected(503,lambda:DeviceAuthenticator(self.registry,self.nonces))

    def test_cached_registry_observes_device_disable_without_restart(self):
        from .device_auth import configured_authenticator
        auth=configured_authenticator(str(self.registry),str(self.nonces))
        self.accept(auth=auth)
        data=json.loads(self.registry.read_text());data['devices']['esp32-test']['enabled']=False
        replacement=self.registry.with_suffix('.replacement')
        replacement.write_text(json.dumps(data));replacement.chmod(0o600);replacement.replace(self.registry)
        reloaded=configured_authenticator(str(self.registry),str(self.nonces))
        self.assertIsNot(auth,reloaded)
        self.rejected(401,lambda:self.accept(auth=reloaded))

    def test_cached_ledger_loss_fails_closed_without_recreating_database(self):
        self.accept()
        self.nonces.unlink()
        self.rejected(503,lambda:self.accept())
        self.assertFalse(self.nonces.exists())

    def test_cached_ledger_marker_loss_fails_closed(self):
        self.accept()
        self.nonces.with_name(self.nonces.name+'.initialized').unlink()
        self.rejected(503,lambda:self.accept())
