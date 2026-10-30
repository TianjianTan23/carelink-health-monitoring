"""Owned loopback TLS fixtures: inherited socket, bounded logs and lifecycle.

No live service discovery or real configuration. Child retains all warning and
tracemalloc settings from its explicit fixture environment.
"""
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time

import httpx
from .process_test_support import warning_environment, CHILD_CHECKS

OBSERVATIONS = []


class TLSProcess:
    def __init__(self, root, target, key, cert, context, *, startup_timeout=60):
        self.root, self.target, self.context = Path(root), target, context
        self.key, self.cert = str(key), str(cert)
        self.startup_timeout = startup_timeout
        self.socket = socket.socket()
        try:
            self.socket.bind(("127.0.0.1", 0))
            self.port = self.socket.getsockname()[1]
            assert self.port not in (8000, 8443, 9443, 18443, 18444)
            self.url = f"https://localhost:{self.port}"
            self.child = None
            self.log = tempfile.TemporaryFile(mode="w+b")
        except BaseException:
            self.socket.close()
            raise
        self.attempts = []

    def logs(self):
        self.log.flush()
        self.log.seek(0)
        return self.log.read().decode(errors="replace")

    def diagnostic(self, reason):
        # Diagnostics are for generated fixtures only; still redact credential
        # formats before including a bounded tail in a failing assertion.
        text = self.logs()[-6000:]
        text = re.sub(r"cl_s1_[A-Za-z0-9_-]+|[0-9a-fA-F]{32,}", "[REDACTED]", text)
        text = re.sub(r"(?im)^.*(?:password|cookie|api.key|signature|hmac.key|authorization).*$", "[REDACTED LINE]", text)
        return f"{reason}; returncode={self.child.poll() if self.child else None}; last_probe={getattr(self,'last_probe','none')}; child_log_tail:\n{text}"

    def start(self, env, *, expect_ready=True):
        assert self.child is None
        fd = self.socket.fileno()
        code = f"""import socket,time,sys
started=time.monotonic()
print('FIXTURE process_start',flush=True)
import uvicorn
print('FIXTURE uvicorn_imported',round(time.monotonic()-started,3),flush=True)
c=uvicorn.Config({self.target!r},host='127.0.0.1',port={self.port},ssl_keyfile={self.key!r},ssl_certfile={self.cert!r},proxy_headers=False,access_log=False,log_level='info')
c.load()
print('FIXTURE application_imported',round(time.monotonic()-started,3),flush=True)
server=uvicorn.Server(c)
with socket.socket(fileno={fd}) as listener:
    server.run(sockets=[listener])
sys.exit(0 if server.started else 3)
"""
        started = time.monotonic()
        self.last_probe = "not attempted"
        self.child = subprocess.Popen([sys.executable, "-B", "-c", code], cwd=self.root, env=warning_environment(env),
            pass_fds=(fd,), stdout=self.log, stderr=self.log)
        try:
            if not expect_ready:
                self.child.wait(timeout=self.startup_timeout)
                if self.child.returncode == 0:
                    raise AssertionError(self.diagnostic("Expected fail-closed startup"))
                return
            with httpx.Client(verify=self.context, trust_env=False, timeout=0.5) as probe:
                deadline = started + self.startup_timeout
                while time.monotonic() < deadline:
                    if self.child.poll() is not None:
                        raise AssertionError(self.diagnostic("TLS child exited before readiness"))
                    try:
                        status = probe.get(self.url + "/health").status_code
                        self.last_probe = f"HTTP {status}"
                        if status == 200:
                            return
                    except httpx.TransportError as error:
                        self.last_probe = type(error).__name__
                    time.sleep(0.1)
                raise AssertionError(self.diagnostic("Bounded TLS readiness timeout"))
        except BaseException:
            self.stop()
            raise
        finally:
            item = {"target": self.target, "elapsed_seconds": round(time.monotonic()-started,3),
                    "ready": self.last_probe == "HTTP 200", "last_probe": self.last_probe,
                    "expected_ready": expect_ready, "startup_timeout": self.startup_timeout,
                    "child_stages": re.findall(r"^FIXTURE .*",self.logs(), re.M)}
            self.attempts.append(item)
            OBSERVATIONS.append(item)
            print("TLS_FIXTURE " + json.dumps(item,sort_keys=True),file=sys.stderr)

    def stop(self):
        if self.child is not None:
            try:
                if self.child.poll() is None:
                    self.child.terminate()
                try:
                    self.child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.child.kill()
                    self.child.wait(timeout=5)
            finally:
                self.child = None
            warning_count = self.logs().count("ResourceWarning:")
            CHILD_CHECKS.append(warning_count)
            print(f"TLS_CHILD_RESOURCE_WARNINGS {warning_count}",file=sys.stderr)
            if warning_count:
                raise AssertionError(self.diagnostic("Child ResourceWarning detected"))

    def close(self):
        try:
            self.stop()
        finally:
            self.socket.close()
            self.log.close()
