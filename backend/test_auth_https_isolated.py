"""Actual loopback TLS/process restart; never connects to existing services."""
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import tempfile
import unittest

import httpx
from .tls_test_support import TLSProcess
from .web_auth import AuthStore, hash_password
from .test_web_auth import PASSWORD

ROOT = Path(__file__).resolve().parents[1]


class IsolatedHTTPSRestartTests(unittest.TestCase):
    def test_tls_identity_session_expiration_and_revocation_survive_process_restart(self):
        openssl=shutil.which("openssl")
        self.assertIsNotNone(openssl,"Local OpenSSL required for isolated TLS fixture")
        with tempfile.TemporaryDirectory(prefix="carelink-auth-tls-") as directory:
            private=Path(directory)
            key,cert=private/"test-only.key",private/"test-only.pem"
            old=os.umask(0o077)
            try:
                subprocess.run([openssl,"req","-x509","-newkey","rsa:2048","-nodes","-days","1",
                                "-subj","/CN=localhost","-addext","subjectAltName=DNS:localhost",
                                "-keyout",str(key),"-out",str(cert)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)
            finally:os.umask(old)
            auth=AuthStore(private/"accounts/auth.db")
            auth.initialize({"fixture_patient":{"password_hash":hash_password(PASSWORD),"role":"patient","mode":"basic","patient_ids":["ttj"],"needs_password_rotation":0}})
            context=ssl.create_default_context(cafile=str(cert))
            fixture=TLSProcess(ROOT,'backend.app:app',key,cert,context)
            self.addCleanup(fixture.close)
            port=fixture.port
            env={k:v for k,v in os.environ.items() if not k.startswith("CARELINK_")}
            from .device_auth_test_support import fixture_device_control
            env.update(fixture_device_control(private))
            env.update({"CARELINK_AUTH_DATABASE_PATH":str(auth.path),"CARELINK_DATABASE_PATH":str(private/"readings.db"),
                        "CARELINK_DEVICE_NONCE_DB":str(private/"unused-nonces.db"),
                        "CARELINK_DEVICE_REGISTRY":str(private/"missing-device-registry.json"),
                        "CARELINK_WEB_ORIGINS":f"https://localhost:{port}","PYTHONDONTWRITEBYTECODE":"1"})
            base=fixture.url
            headers={"Origin":base,"X-CareLink-CSRF":"1"}
            def start():
                fixture.start(env)
                return fixture.child
            def stop(child):
                fixture.stop()
            process=None

            try:
                process=start()
                # Neither a different identity nor a missing trust anchor works.
                with httpx.Client(verify=context,trust_env=False,timeout=2) as client:
                    with self.assertRaises(httpx.ConnectError):client.get(f"https://127.0.0.1:{port}/health")
                with httpx.Client(verify=ssl.create_default_context(),trust_env=False,timeout=2) as client:
                    with self.assertRaises(httpx.ConnectError):client.get(base+"/health")
                clients=[httpx.Client(base_url=base,verify=context,trust_env=False,timeout=5) for _ in range(3)]
                try:
                    for client in clients:
                        self.assertEqual(client.post("/api/login",headers=headers,json={"username":"fixture_patient","password":PASSWORD}).status_code,200)
                        self.assertEqual(client.get("/api/patients/ttj/readings").status_code,200)
                    old_token=clients[1].cookies.get("carelink_session")
                    self.assertEqual(clients[1].post("/api/logout",headers=headers,json={}).status_code,200)
                    # Reuse exactly the pre-logout cookie in memory, not a file.
                    clients[1].cookies.set("carelink_session",old_token)
                    from .web_auth import token_hash
                    with auth.connect() as db, db:
                        db.execute("UPDATE sessions SET expires_at=1 WHERE token_hash=?",(token_hash(clients[2].cookies.get("carelink_session")),))
                    self.assertEqual(clients[1].get("/api/patients/ttj/readings").status_code,401)
                    self.assertEqual(clients[2].get("/api/patients/ttj/readings").status_code,401)
                    stop(process);process=None
                    process=start()
                    for client,expected in zip(clients,(200,401,401)):
                        self.assertEqual(client.get("/api/session").status_code,expected)
                        self.assertEqual(client.get("/api/patients/ttj/readings").status_code,expected)
                finally:
                    for client in clients:client.close()
            finally:stop(process)


if __name__=="__main__":unittest.main()
