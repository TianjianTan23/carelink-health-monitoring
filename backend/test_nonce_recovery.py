"""Synthetic files/processes only. Never uses real gateway configuration."""
from concurrent.futures import ThreadPoolExecutor
import contextlib
import importlib
import io
import json
import os
from pathlib import Path
import sqlite3
from contextlib import closing, ExitStack
from .process_test_support import reap_process, start_process, checked_run
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from . import nonce_ledger as ledger
from .device_auth import DeviceAuthError
from .device_auth_test_support import fixture_credentials, fixture_web_config, signed_headers, write_registry

ROOT = Path(__file__).resolve().parents[1]


class NonceRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="carelink-nonce-recovery-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / "synthetic.sqlite3"
        self.marker = self.path.with_name(self.path.name + ".initialized")
        self.intent = self.path.with_name(self.path.name + ".initializing")

    def test_sidecar_removed_between_stat_and_access_is_not_a_permission_failure(self):
        self.seed();store=ledger.NonceStore(self.path)
        side=self.path.with_name(self.path.name+'-shm');side.write_bytes(b'');side.chmod(0o600)
        original=ledger.os.access
        def removed(path,mode):
            if Path(path)==side:
                side.unlink()
                return False
            return original(path,mode)
        with patch.object(ledger.os,'access',side_effect=removed):
            store._paths()  # Missing idle sidecar is allowed; SQLite recreates it.
        self.assertFalse(side.exists());self.assertEqual(self.count(),1)

    def test_existing_sidecar_access_denial_stays_fail_closed(self):
        self.seed();store=ledger.NonceStore(self.path)
        side=self.path.with_name(self.path.name+'-shm');side.write_bytes(b'');side.chmod(0o600)
        original=ledger.os.access
        def denied(path,mode):return False if Path(path)==side else original(path,mode)
        try:
            with patch.object(ledger.os,'access',side_effect=denied):self.rejected(store._paths)
            self.assertTrue(side.exists())
        finally:side.unlink()
        self.assertEqual(self.count(),1)

    def test_orphaned_control_binding_forbids_new_installation_initialization(self):
        binding=self.path.with_name(self.path.name+'.control')
        binding.write_bytes(b'synthetic managed authority evidence\n');binding.chmod(0o600)
        self.rejected(self.initialize)
        self.assertFalse(self.path.exists());self.assertFalse(self.marker.exists());self.assertFalse(self.intent.exists())
        self.assertEqual(binding.read_bytes(),b'synthetic managed authority evidence\n')

    def initialize(self, path=None):
        ledger.initialize_new_ledger(path or self.path, authorization=ledger.AUTHORIZATION)

    def rejected(self, fn, status=503):
        with self.assertRaises(DeviceAuthError) as error:
            fn()
        self.assertEqual(error.exception.status, status)
        self.assertIn(error.exception.detail, (ledger.UNAVAILABLE, "Device request replay rejected"))

    def count(self):
        with closing(sqlite3.connect(self.path.as_uri()+"?mode=ro", uri=True)) as db, db:
            return db.execute("SELECT count(*) FROM device_nonces").fetchone()[0]

    def reserve(self, store=None, nonce="1"*32):
        (store or ledger.NonceStore(self.path)).reserve("fixture-device", nonce, int(time.time()), int(time.time()))

    def seed(self):
        self.initialize()
        self.reserve()

    def test_both_missing_never_create_anything(self):
        self.rejected(lambda: ledger.NonceStore(self.path))
        self.assertEqual(list(self.root.iterdir()), [])

    def test_missing_parent_is_not_created(self):
        self.rejected(lambda: ledger.NonceStore(self.root/"missing"/"ledger.db"))
        self.assertFalse((self.root/"missing").exists())

    def test_ledger_missing_marker_preserved(self):
        self.seed(); before = self.marker.read_bytes(); self.path.unlink()
        self.rejected(lambda: ledger.NonceStore(self.path))
        self.assertFalse(self.path.exists()); self.assertEqual(self.marker.read_bytes(), before)

    def test_marker_missing_history_preserved(self):
        self.seed(); self.marker.unlink(); before = self.path.read_bytes()
        self.rejected(lambda: ledger.NonceStore(self.path))
        self.assertFalse(self.marker.exists()); self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.count(), 1)

    def test_zero_length_ledger_is_not_repaired(self):
        self.seed(); self.path.write_bytes(b"")
        self.rejected(lambda: ledger.NonceStore(self.path))
        self.assertEqual(self.path.read_bytes(), b"")

    def test_corrupt_ledger_is_not_repaired(self):
        self.seed(); damaged = b"synthetic damaged SQLite"*100; self.path.write_bytes(damaged)
        self.rejected(lambda: ledger.NonceStore(self.path))
        self.assertEqual(self.path.read_bytes(), damaged)

    def test_truncated_page_is_rejected(self):
        self.seed(); self.path.write_bytes(self.path.read_bytes()[:600]); before = self.path.read_bytes()
        self.rejected(lambda: ledger.NonceStore(self.path))
        self.assertEqual(self.path.read_bytes(), before)

    def test_empty_marker_is_not_repaired(self):
        self.seed(); self.marker.write_bytes(b"")
        self.rejected(lambda: ledger.NonceStore(self.path)); self.assertEqual(self.count(), 1)
        self.assertEqual(self.marker.read_bytes(), b"")

    def test_malformed_duplicate_key_or_wrong_version_marker_is_rejected(self):
        self.seed()
        for value in [b"partial{", b'{"format":2,"format":2,"ledger_id":"'+b"1"*32+b'"}\n',
                      b'{"format":1,"ledger_id":"'+b"1"*32+b'"}\n']:
            self.marker.write_bytes(value)
            self.rejected(lambda: ledger.NonceStore(self.path))
        self.assertEqual(self.count(), 1)

    def test_legacy_v1_is_not_automatically_adopted(self):
        # Genuine v1 schema, rather than a v2 file with just an old marker.
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute(ledger.SCHEMA["device_nonces"])
            db.execute("INSERT INTO device_nonces VALUES (?,?,?,?)", ("fixture-device", "1"*32, int(time.time()), int(time.time())))
        self.path.chmod(0o600)
        self.marker.write_text("CareLink persistent device nonce ledger v1\n"); self.marker.chmod(0o600)
        before = self.path.read_bytes()
        self.rejected(lambda: ledger.NonceStore(self.path))
        self.assertEqual(self.path.read_bytes(), before); self.assertEqual(self.count(), 1)

    def test_marker_from_another_ledger_rejected(self):
        self.seed(); other = self.root/"other.sqlite3"; self.initialize(other)
        self.marker.write_bytes(other.with_name(other.name+".initialized").read_bytes())
        self.rejected(lambda: ledger.NonceStore(self.path)); self.assertEqual(self.count(), 1)

    def test_metadata_identity_mismatch_rejected(self):
        self.seed()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE nonce_metadata SET ledger_id=?", ("0"*32,))
        self.rejected(lambda: ledger.NonceStore(self.path)); self.assertEqual(self.count(), 1)

    def test_history_count_mismatch_rejected(self):
        self.seed()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE nonce_metadata SET admissions=0")
        self.rejected(lambda: ledger.NonceStore(self.path)); self.assertEqual(self.count(), 1)

    def test_removed_protection_trigger_rejected(self):
        self.seed()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("DROP TRIGGER nonce_no_delete")
        self.rejected(lambda: ledger.NonceStore(self.path)); self.assertEqual(self.count(), 1)

    def test_append_only_history_cannot_be_updated_or_deleted(self):
        self.seed()
        for sql in ["DELETE FROM device_nonces", "UPDATE device_nonces SET signed_at=0"]:
            with closing(sqlite3.connect(self.path)) as db, db:
                with self.assertRaises(sqlite3.IntegrityError): db.execute(sql)
        self.assertEqual(self.count(), 1)

    def test_unreadable_or_unwritable_ledger_rejected_without_chmod(self):
        self.seed()
        for mode in (0o000, 0o200, 0o400, 0o640):
            self.path.chmod(mode)
            self.rejected(lambda: ledger.NonceStore(self.path))
            self.assertEqual(self.path.stat().st_mode & 0o777, mode)
        self.path.chmod(0o600); self.assertEqual(self.count(), 1)

    def test_unreadable_or_unwritable_marker_rejected_without_chmod(self):
        self.seed()
        for mode in (0o000, 0o200, 0o400, 0o644):
            self.marker.chmod(mode)
            self.rejected(lambda: ledger.NonceStore(self.path))
            self.assertEqual(self.marker.stat().st_mode & 0o777, mode)
        self.marker.chmod(0o600); self.assertEqual(self.count(), 1)

    def test_unwritable_or_unreadable_directory_rejected_without_chmod(self):
        self.seed()
        try:
            for mode in (0o500, 0o300, 0o750):
                self.root.chmod(mode)
                self.rejected(lambda: ledger.NonceStore(self.path))
                self.assertEqual(self.root.stat().st_mode & 0o777, mode)
        finally: self.root.chmod(0o700)
        self.assertEqual(self.count(), 1)

    def test_ledger_symlink_rejected(self):
        self.seed(); actual = self.root/"preserved.db"; self.path.rename(actual); self.path.symlink_to(actual)
        self.rejected(lambda: ledger.NonceStore(self.path)); self.assertEqual(self.count(), 1)

    def test_marker_symlink_rejected(self):
        self.seed(); actual = self.root/"preserved.marker"; self.marker.rename(actual); self.marker.symlink_to(actual)
        self.rejected(lambda: ledger.NonceStore(self.path)); self.assertEqual(self.count(), 1)

    def test_hardlinked_ledger_rejected(self):
        self.seed(); os.link(self.path, self.root/"alias.db")
        self.rejected(lambda: ledger.NonceStore(self.path)); self.assertEqual(self.count(), 1)

    def test_unsafe_sidecar_rejected(self):
        self.seed(); sidecar = self.path.with_name(self.path.name+"-wal")
        sidecar.symlink_to(self.root/"missing")
        self.rejected(lambda: ledger.NonceStore(self.path))
        self.assertTrue(sidecar.is_symlink())

    def test_cached_store_detects_loss_of_both_files(self):
        self.seed(); store = ledger.NonceStore(self.path); self.path.unlink(); self.marker.unlink()
        self.rejected(lambda: self.reserve(store, "2"*32))
        self.assertFalse(self.path.exists()); self.assertFalse(self.marker.exists())

    def test_cached_store_detects_replaced_pair(self):
        self.seed(); store = ledger.NonceStore(self.path)
        self.path.rename(self.root/"preserved.db"); self.marker.rename(self.root/"preserved.marker")
        self.initialize()
        self.rejected(lambda: self.reserve(store, "2"*32)); self.assertEqual(self.count(), 0)
        with closing(sqlite3.connect(self.root/"preserved.db")) as db, db:
            self.assertEqual(db.execute("SELECT count(*) FROM device_nonces").fetchone()[0], 1)

    def test_restart_keeps_replay_rejected(self):
        self.seed(); self.rejected(lambda: self.reserve(), 409); self.assertEqual(self.count(), 1)

    def test_initialization_requires_explicit_authorization(self):
        self.rejected(lambda: ledger.initialize_new_ledger(self.path, authorization=""))
        self.assertEqual(list(self.root.iterdir()), [])

    def test_initializer_never_overwrites_existing_history(self):
        self.seed(); before = self.path.read_bytes()
        self.rejected(self.initialize)
        self.assertEqual(self.path.read_bytes(), before); self.assertEqual(self.count(), 1)
        self.assertFalse(self.intent.exists())

    def test_initializer_refuses_orphan_marker(self):
        self.seed(); self.path.unlink(); self.rejected(self.initialize); self.assertFalse(self.path.exists())

    def test_initializer_refuses_orphan_ledger(self):
        self.seed(); self.marker.unlink(); self.rejected(self.initialize)
        self.assertFalse(self.marker.exists()); self.assertEqual(self.count(), 1)

    def test_initializer_refuses_empty_file(self):
        self.path.touch(mode=0o600); self.rejected(self.initialize)
        self.assertEqual(self.path.read_bytes(), b""); self.assertFalse(self.marker.exists())

    def test_initializer_refuses_orphan_wal_or_dangling_symlink(self):
        artifact = self.path.with_name(self.path.name+"-wal"); artifact.touch(mode=0o600)
        self.rejected(self.initialize); artifact.unlink(); self.path.symlink_to(self.root/"missing")
        self.rejected(self.initialize); self.assertFalse(self.marker.exists())

    def test_incomplete_intent_blocks_even_valid_pair(self):
        self.seed(); self.intent.write_text("incomplete"); self.intent.chmod(0o600)
        self.rejected(lambda: ledger.NonceStore(self.path)); self.rejected(self.initialize)
        self.assertEqual(self.count(), 1); self.assertTrue(self.intent.exists())

    def test_partial_marker_write_stays_quarantined(self):
        def broken_dump(value, stream, **kwargs):
            stream.write('{"format":'); stream.flush(); raise OSError("Synthetic disk failure")
        with patch.object(ledger.json, "dump", broken_dump): self.rejected(self.initialize)
        self.assertTrue(self.intent.exists()); self.assertTrue(self.path.exists())
        self.rejected(lambda: ledger.NonceStore(self.path)); self.rejected(self.initialize)

    def test_partial_schema_write_stays_quarantined(self):
        with patch.dict(ledger.SCHEMA, {"synthetic_bad": "INVALID SQL"}): self.rejected(self.initialize)
        self.assertTrue(self.intent.exists()); self.assertTrue(self.path.exists()); self.assertFalse(self.marker.exists())
        self.rejected(lambda: ledger.NonceStore(self.path)); self.rejected(self.initialize)

    def test_failure_to_publish_durable_pair_keeps_intent(self):
        actual = ledger._fsync_directory; calls = []
        def interrupted(path):
            calls.append(1)
            if len(calls) == 2: raise OSError("Synthetic fsync failure")
            actual(path)
        with patch.object(ledger, "_fsync_directory", interrupted): self.rejected(self.initialize)
        self.assertTrue(self.intent.exists()); self.rejected(lambda: ledger.NonceStore(self.path))

    def test_process_exit_during_initialization_never_enables_recovery(self):
        for stage in ("intent", "database", "pair"):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory(dir=self.root) as directory:
                path = Path(directory)/"test.db"
                code = '''import os,sys
from pathlib import Path
from backend import nonce_ledger as m
stage=sys.argv[2]
original=m._fsync_directory
calls=0
def stop_after(path):
 global calls
 calls+=1
 original(path)
 if (stage=="intent" and calls==1) or (stage=="pair" and calls==2): os._exit(73)
m._fsync_directory=stop_after
if stage=="database":
 original_sqlite=m._sqlite
 def stopped(path): os._exit(73)
 m._sqlite=stopped
m.initialize_new_ledger(Path(sys.argv[1]),authorization=m.AUTHORIZATION)
'''
                result = checked_run([sys.executable, "-c", code, str(path), stage], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
                self.assertEqual(result.returncode, 73)
                self.rejected(lambda: ledger.NonceStore(path))
                self.rejected(lambda: self.initialize(path))
                self.assertTrue(path.with_name(path.name+".initializing").exists())

    def test_concurrent_initializers_only_one_creates(self):
        code = '''import sys
from pathlib import Path
from backend.nonce_ledger import initialize_new_ledger, AUTHORIZATION
from backend.device_auth_errors import DeviceAuthError
try: initialize_new_ledger(Path(sys.argv[1]),authorization=AUTHORIZATION); print(200)
except DeviceAuthError as e: print(e.status)
'''
        with ExitStack() as processes:
            children=[]
            for _ in range(8):
                child=start_process([sys.executable,"-c",code,str(self.path)],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                processes.callback(reap_process,child);children.append(child)
            statuses = [int(child.communicate(timeout=30)[0].strip()) for child in children]
        self.assertEqual(statuses.count(200), 1); self.assertEqual(statuses.count(503), 7)
        ledger.NonceStore(self.path); self.assertEqual(self.count(), 0); self.assertFalse(self.intent.exists())

    def test_concurrent_process_reservations_only_one_commits(self):
        self.initialize()
        code = '''import json,sys,time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from backend.nonce_ledger import NonceStore
from backend.device_auth_errors import DeviceAuthError
def send(_):
 try:
  NonceStore(Path(sys.argv[1])).reserve("fixture-device","a"*32,int(time.time()),int(time.time())); return 200
 except DeviceAuthError as e: return e.status
with ThreadPoolExecutor(max_workers=4) as pool: print(json.dumps(list(pool.map(send,range(8)))))
'''
        with ExitStack() as processes:
            children=[]
            for _ in range(2):
                child=start_process([sys.executable,"-c",code,str(self.path)],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                processes.callback(reap_process,child);children.append(child)
            statuses = sum([json.loads(child.communicate(timeout=30)[0]) for child in children], [])
        self.assertEqual(statuses.count(200), 1); self.assertEqual(statuses.count(409), 15)
        self.assertEqual(self.count(), 1)

    def test_interrupted_transaction_preserves_history_and_rolls_back_partial_insert(self):
        self.seed(); store = ledger.NonceStore(self.path)
        with self.assertRaises(KeyboardInterrupt):
            with store.connect() as db:
                db.execute("INSERT INTO device_nonces VALUES (?,?,?,?)", ("fixture-device", "2"*32, int(time.time()), int(time.time())))
                raise KeyboardInterrupt()
        self.assertEqual(self.count(), 1); self.rejected(lambda: self.reserve(), 409)
        self.reserve(nonce="2"*32); self.assertEqual(self.count(), 2)

    def test_process_exit_rolls_back_uncommitted_nonce_but_keeps_committed_history(self):
        self.seed()
        code = '''import os,sys,time
from pathlib import Path
from backend.nonce_ledger import NonceStore
with NonceStore(Path(sys.argv[1])).connect() as db:
 db.execute("INSERT INTO device_nonces VALUES (?,?,?,?)",("fixture-device","2"*32,int(time.time()),int(time.time())))
 os._exit(73)
'''
        child = checked_run([sys.executable, "-c", code, str(self.path)], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        self.assertEqual(child.returncode, 73)
        self.assertEqual(self.count(), 1); self.rejected(lambda: self.reserve(), 409)
        self.reserve(nonce="2"*32); self.assertEqual(self.count(), 2)

    def test_storage_open_error_is_fail_closed(self):
        self.seed()
        with patch.object(ledger, "_sqlite", side_effect=sqlite3.OperationalError("Synthetic I/O error")):
            self.rejected(lambda: ledger.NonceStore(self.path))
        self.assertEqual(self.count(), 1)

    def test_os_denied_readwrite_probe_on_ledger_or_marker_is_fail_closed(self):
        self.seed(); actual = ledger.os.access
        for target in (self.path, self.marker):
            def denied(path, mode, *args, **kwargs):
                return False if Path(path)==target else actual(path,mode,*args,**kwargs)
            with patch.object(ledger.os, "access", denied):
                self.rejected(lambda: ledger.NonceStore(self.path))
        self.assertEqual(self.count(), 1)

    def test_every_reservation_runs_full_structural_check(self):
        self.seed(); store = ledger.NonceStore(self.path)
        with patch.object(store, "_validate", wraps=store._validate) as check:
            self.reserve(store, "2"*32)
            self.assertTrue(check.call_args.args[2])
        self.assertEqual(self.count(), 2)

    def test_close_error_is_normalized_to_unavailable(self):
        self.seed(); actual = ledger._sqlite
        class BrokenClose:
            def __init__(self, db): self.db = db
            def __getattr__(self, name): return getattr(self.db, name)
            def close(self):
                self.db.close()
                raise sqlite3.OperationalError("Synthetic close I/O failure")
        with patch.object(ledger, "_sqlite", lambda p: BrokenClose(actual(p))):
            self.rejected(lambda: ledger.NonceStore(self.path))
        self.assertEqual(self.count(), 1)

    def test_commit_failure_does_not_admit_or_erase_history(self):
        self.seed(); store = ledger.NonceStore(self.path); actual = ledger._sqlite
        class BrokenCommit:
            def __init__(self, db): self.db = db
            def __getattr__(self, name): return getattr(self.db, name)
            def commit(self): raise sqlite3.OperationalError("Synthetic full disk")
        with patch.object(ledger, "_sqlite", lambda p: BrokenCommit(actual(p))):
            self.rejected(lambda: self.reserve(store, "2"*32))
        self.assertEqual(self.count(), 1); self.rejected(lambda: self.reserve(), 409)


class RecoveryIngressTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="carelink-recovery-api-")
        self.addCleanup(self.tmp.cleanup); self.root = Path(self.tmp.name)
        self.path = self.root/"auth/nonce.db"; self.registry = self.root/"auth/devices.json"
        self.marker = self.path.with_name(self.path.name+".initialized")
        self.database = self.root/"readings.db"
        write_registry(self.registry)
        ledger.initialize_new_ledger(self.path, authorization=ledger.AUTHORIZATION)
        self.env = patch.dict(os.environ, {**fixture_web_config(self.root, self.path),
            "CARELINK_DEVICE_REGISTRY": str(self.registry), "CARELINK_DEVICE_NONCE_DB": str(self.path)})
        self.env.start(); self.addCleanup(self.env.stop)
        self.app = importlib.import_module("backend.app")
        self.ingress = importlib.import_module("backend.device_ingress")
        self.dbpatch = patch.object(self.app, "DATABASE_PATH", self.database)
        self.dbpatch.start(); self.addCleanup(self.dbpatch.stop)
        self.body = b'{"device_id":"esp32-test","object_temp_c":36.5}'

    def test_startup_missing_pair_fails_before_readings_database_creation(self):
        self.path.unlink(); self.marker.unlink()
        with self.assertRaises(DeviceAuthError) as error:
            with TestClient(self.ingress.app, base_url="https://testserver"): pass
        self.assertEqual(error.exception.status, 503)
        self.assertFalse(self.database.exists()); self.assertFalse(self.path.exists()); self.assertFalse(self.marker.exists())

    def test_runtime_lost_pair_returns_503_and_never_writes_sensor_data(self):
        with TestClient(self.ingress.app, base_url="https://testserver") as client:
            self.assertEqual(client.get("/health").status_code, 200)
            self.path.unlink(); self.marker.unlink()
            with patch.object(ledger, "initialize_new_ledger", side_effect=AssertionError("Must not initialize")):
                self.assertEqual(client.get("/health").status_code, 503)
                response = client.post("/sensor-data", content=self.body, headers=signed_headers(self.body))
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json(), {"detail": "Device reception frozen or unavailable"})
            with closing(sqlite3.connect(self.database)) as db, db:
                self.assertEqual(db.execute("SELECT count(*) FROM readings").fetchone()[0], 0)
            self.assertFalse(self.path.exists()); self.assertFalse(self.marker.exists())

    def test_runtime_marker_failure_has_no_secret_logs_or_new_readings(self):
        output = io.StringIO()
        headers = signed_headers(self.body)
        with TestClient(self.ingress.app, base_url="https://testserver") as client:
            self.marker.write_bytes(b"incomplete marker")
            with self.assertLogs("httpx", level="INFO") as logs, contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                response = client.post("/sensor-data", content=self.body, headers=headers)
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json(), {"detail": "Device reception frozen or unavailable"})
            text = output.getvalue()+"\n".join(logs.output)+response.text
            for name, value in headers.items():
                if name.lower() in {"x-carelink-api-key", "x-carelink-signature", "x-carelink-nonce"}:
                    self.assertNotIn(value, text)
            self.assertNotIn(fixture_credentials("esp32-test")[1].hex(), text)
            self.assertNotIn("Traceback", text)
            with closing(sqlite3.connect(self.database)) as db, db:
                self.assertEqual(db.execute("SELECT count(*) FROM readings").fetchone()[0], 0)
