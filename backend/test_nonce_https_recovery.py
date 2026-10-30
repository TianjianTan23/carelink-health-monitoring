"""Disposable TLS receiver only; localhost, OS allocated port, synthetic secrets."""
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import sqlite3
import ssl
import subprocess
import tempfile
import unittest

import httpx
from .device_auth_test_support import fixture_credentials, signed_headers, write_registry
from .nonce_ledger import AUTHORIZATION, initialize_new_ledger
from .tls_test_support import TLSProcess

ROOT = Path(__file__).resolve().parents[1]


class NonceHTTPSRecoveryTests(unittest.TestCase):
    def test_tls_receiver_restart_retains_nonce_and_missing_pair_blocks_cold_start(self):
        openssl = shutil.which("openssl")
        self.assertIsNotNone(openssl)
        with tempfile.TemporaryDirectory(prefix="carelink-nonce-tls-") as directory:
            root = Path(directory); registry = root/"devices.json"; ledger = root/"nonce.db"
            marker = ledger.with_name(ledger.name+".initialized"); readings = root/"readings.db"
            key, cert = root/"synthetic.key", root/"synthetic.pem"
            write_registry(registry); initialize_new_ledger(ledger, authorization=AUTHORIZATION)
            old = os.umask(0o077)
            try:
                subprocess.run([openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                    "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost", "-keyout", str(key), "-out", str(cert)],
                    check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
            finally: os.umask(old)
            context = ssl.create_default_context(cafile=str(cert))
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            fixture=TLSProcess(ROOT,'backend.device_ingress:app',key,cert,context)
            self.addCleanup(fixture.close)
            port=fixture.port
            env = {k:v for k,v in os.environ.items() if not k.startswith("CARELINK_")}
            from .device_auth_test_support import fixture_device_control
            env.update(fixture_device_control(root,ledger))
            env.update({"CARELINK_DATABASE_PATH":str(readings), "CARELINK_DEVICE_NONCE_DB":str(ledger),
                "CARELINK_DEVICE_REGISTRY":str(registry), "CARELINK_AUTH_DATABASE_PATH":str(root/"unused-auth.db"),
                "PYTHONDONTWRITEBYTECODE":"1"})
            url = fixture.url
            def stop():
                fixture.stop()
            def start(expect_ready=True):
                fixture.start(env,expect_ready=expect_ready)

            body = b'{"device_id":"esp32-test","object_temp_c":36.5}'
            headers = signed_headers(body)
            try:
                start()
                with httpx.Client(verify=context, trust_env=False, timeout=3) as client:
                    with self.assertRaises(httpx.ConnectError): client.get(f"https://127.0.0.1:{port}/health")
                    self.assertEqual(client.post(url+"/sensor-data", content=body, headers=headers).status_code, 200)
                stop(); start()
                with httpx.Client(verify=context, trust_env=False, timeout=3) as client:
                    self.assertEqual(client.post(url+"/sensor-data", content=body, headers=headers).status_code, 409)
                    # Simulated storage loss AFTER readiness: fail closed at both
                    # health and POST, never recreate files or write readings.
                    ledger.rename(root/"preserved-ledger.db"); marker.rename(root/"preserved-marker")
                    self.assertEqual(client.get(url+"/health").status_code, 503)
                    self.assertEqual(client.post(url+"/sensor-data", content=body, headers=signed_headers(body)).status_code, 503)
                stop()
                start(expect_ready=False)
                self.assertFalse(ledger.exists()); self.assertFalse(marker.exists())
                with closing(sqlite3.connect(readings.as_uri()+"?mode=ro", uri=True)) as db, db:
                    self.assertEqual(db.execute("SELECT count(*) FROM readings").fetchone()[0], 1)
                text = fixture.logs()
                for name, value in headers.items():
                    if name.lower() in {"x-carelink-api-key", "x-carelink-signature", "x-carelink-nonce"}:
                        self.assertNotIn(value, text)
                self.assertNotIn(fixture_credentials("esp32-test")[1].hex(), text)
            finally: stop()
