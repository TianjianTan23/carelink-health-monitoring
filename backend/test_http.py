"""Real HTTP socket tests, including Java/Node clients. All credentials are ephemeral."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import httpx
from .test_support import PASSWORDS

ROOT = Path(__file__).resolve().parents[1]


class HTTPIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="carelink-http-test-")
        cls.directory = Path(cls.temp.name)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        cls.url = f"http://127.0.0.1:{port}"
        cls.env = {**os.environ, "CARELINK_DATABASE_PATH": str(cls.directory / "http.db"),
                   "CARELINK_ENV_FILE": str(cls.directory / "absent.env"),
                   "CARELINK_PORT": str(port), "CARELINK_BIND_HOST": "127.0.0.1"}
        cls.log = open(cls.directory / "server.log", "wb")
        cls.process = subprocess.Popen([sys.executable, "scripts/serve-local.py"], cwd=ROOT, env=cls.env, stdout=cls.log, stderr=cls.log)
        ready = False
        for _ in range(150):
            if cls.process.poll() is not None:
                break
            try:
                r = httpx.get(cls.url + "/health", trust_env=False, timeout=1)
                if r.status_code == 200:
                    ready = True
                    break
            except httpx.HTTPError:
                pass
            time.sleep(.2)
        if not ready:
            cls.process.terminate(); cls.process.wait(timeout=10); cls.log.close()
            raise RuntimeError("Temporary HTTP test server failed to start; no credentials were logged")

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate(); cls.process.wait(timeout=15); cls.log.close()
        cls.temp.cleanup()

    def sensor(self):
        body = json.dumps(dict(device_id="security-test", heart_rate_bpm=75, object_temp_c=36.6, fall_detected=False)).encode()
        return httpx.post(self.url + "/sensor-data", content=body, headers={"Content-Type":"application/json"}, trust_env=False)

    def test_verified_http_login_data_logout(self):
        self.assertEqual(self.sensor().status_code, 200)
        with httpx.Client(base_url=self.url, trust_env=False) as client:
            r = client.post("/api/login", json={"username": "ttj", "password": PASSWORDS["ttj"]})
            self.assertEqual(r.status_code, 200)
            client.headers["X-CSRF-Token"] = r.json()["csrfToken"]
            self.assertEqual(client.get("/api/patients").status_code, 200)
            self.assertEqual(client.post("/api/logout").status_code, 200)
            self.assertEqual(client.get("/api/session").status_code, 401)


    def test_node_simulator(self):
        env = {**self.env, "CARELINK_ENV_FILE": str(self.directory / "absent.env")}
        result = subprocess.run(["node", "scripts/simulate-sensor.mjs", "--url=" + self.url + "/sensor-data", "--count=1", "--scenario=normal"], cwd=ROOT, env=env, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, "Node HTTP simulator interoperability failed")

    def test_hardware_free_launcher_isolates_database_and_cleans_up(self):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        config_file = self.directory / "demo.env"
        # Only ephemeral test credentials; private file permissions, no values in logs.
        settings = {key:value for key,value in self.env.items() if key.startswith("CARELINK_") and key != "CARELINK_ENV_FILE"}
        config_file.touch(mode=0o600)
        config_file.write_text("\n".join(f"{key}='{value}'" for key,value in settings.items()) + "\n")
        database = self.directory / "synthetic.db"
        env = {**self.env, "CARELINK_ENV_FILE":str(config_file), "CARELINK_DEMO_PORT":str(port),
               "CARELINK_SIMULATION_DATABASE":str(database), "CARELINK_NO_BROWSER":"1"}
        result = subprocess.run([sys.executable,"scripts/run-without-hardware.py","--check"], cwd=ROOT, env=env, capture_output=True, timeout=50)
        self.assertEqual(result.returncode, 0, "Isolated HTTP demo failed")
        import sqlite3
        with sqlite3.connect(database) as db:
            rows = db.execute("SELECT raw_json FROM readings").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(json.loads(rows[0][0])["source"], "synthetic")
        with socket.socket() as sock:
            self.assertNotEqual(sock.connect_ex(("127.0.0.1",port)), 0, "Demo server must stop after the check")

    @unittest.skipUnless(os.environ.get("JAVA_HOME") and os.environ.get("CARELINK_JSON_JAR"), "Set JAVA_HOME and CARELINK_JSON_JAR for real native Java HTTP tests")
    def test_android_java_http_cookie_csrf(self):
        self.assertEqual(self.sensor().status_code, 200)
        env = {**self.env, "CARELINK_TEST_USER":"wyn", "CARELINK_TEST_PASSWORD":PASSWORDS["wyn"]}
        result = subprocess.run(["sh", "android/test-core.sh", self.url], env=env, cwd=ROOT, capture_output=True)
        self.assertEqual(result.returncode, 0, "Native Java HTTP login/data/CSRF logout failed")


if __name__ == "__main__":
    unittest.main()
