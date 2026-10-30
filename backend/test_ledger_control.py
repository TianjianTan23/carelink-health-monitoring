"""No real files, sockets, registry or processes; synthetic temporary fixtures."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
from contextlib import closing
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from fastapi import Depends
from fastapi.testclient import TestClient
from . import ledger_control as lc
from .device_auth import authenticated_sensor_payload,DeviceAuthError
from .device_auth_test_support import write_registry,signed_headers
from .controlled_device_ingress import create_app
from .nonce_ledger import NonceStore,SCHEMA
from .write_gate import write_lease
from .process_test_support import reap_process, start_process, checked_run


class LedgerControlTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="carelink-managed-migration-");self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.source=self.root/"source.db";self.control=self.root/"control"
        lc.private_new(self.source,b"")  # Sidecars inherit the original DB mode.
        with closing(sqlite3.connect(self.source)) as db, db:
            db.execute("PRAGMA journal_mode=WAL");db.execute(SCHEMA["device_nonces"])
            db.executemany("INSERT INTO device_nonces VALUES (?,?,?,?)",[("fixture",f"{i:032x}",1700000000+i,1700000100+i) for i in range(20)])
        self.source.chmod(0o600);lc.private_new(self.source.with_name(self.source.name+".initialized"),b"CareLink persistent device nonce ledger v1\n")
        self.inventory=self.root/"approved-inventory.json";info=self.source.stat()
        with lc.sql(self.source) as db:checkpoint=lc.fingerprint(lc.history(db))
        self.receipt={"all_writers_controlled":True,"legacy_writers_stopped":True,"review_reference":"synthetic-review-only",
            "expires_at":int(time.time())+3600,"source":str(self.source),"device":info.st_dev,"inode":info.st_ino,"checkpoint":checkpoint}
        lc.private_new(self.inventory,(json.dumps(self.receipt)+"\n").encode())

    def enroll(self):return lc.Controller.enroll(self.control,self.source,self.inventory)
    def ready(self):
        c=self.enroll();c.prepare("v2");c.switch();c.resume();return c
    def rows(self,path):
        with lc.sql(path) as db:return lc.history(db)
    def rejected(self,fn):
        with self.assertRaises((lc.ControlError,DeviceAuthError,OSError,sqlite3.Error)):fn()

    def test_header_validation_preserves_sqlite_writer_record_lock(self):
        # A separate process must NOT acquire SQLite's pending/reserved byte
        # while this process holds BEGIN IMMEDIATE, even after metadata checks.
        code = """import fcntl,os,sys
fd=os.open(sys.argv[1],os.O_RDWR)
try:
 try:fcntl.lockf(fd,fcntl.LOCK_EX|fcntl.LOCK_NB,510,0x40000002);sys.exit(9)
 except BlockingIOError:sys.exit(0)
finally:os.close(fd)
"""
        with lc.sql(self.source,"rw") as db:
            db.execute("BEGIN IMMEDIATE")
            def locked():
                child=checked_run([sys.executable,"-I","-S","-c",code,str(self.source)],
                    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5)
                self.assertEqual(child.returncode,0,"SQLite writer record lock lost")
            locked()
            lc.validate(self.source,db)
            locked()
            with lc.sql(self.source) as second:
                self.assertEqual(len(lc.history(second)),20)
            locked()

    def test_complete_migration_preserves_all_four_values(self):
        before=self.rows(self.source);c=self.ready();target=Path(c.state()["active"])
        self.assertEqual(before,self.rows(target));self.assertEqual(before,self.rows(self.source))
        for device,nonce,_,_ in before:
            with self.assertRaises(DeviceAuthError) as err:NonceStore(target).reserve(device,nonce,int(time.time()),int(time.time()))
            self.assertEqual(err.exception.status,409)

    def test_invalid_inventory_missing_expired_or_unverified_refused(self):
        for field,value in [("legacy_writers_stopped",False),("all_writers_controlled",False),("expires_at",0),("inode",0),("checkpoint",{})]:
            self.inventory.write_text(json.dumps({**self.receipt,field:value}));self.rejected(self.enroll)
            self.assertFalse(self.control.exists())

    def test_missing_marker_corrupt_source_and_permissions_refused(self):
        marker=self.source.with_name(self.source.name+".initialized");marker.unlink();self.rejected(self.enroll)
        lc.private_new(marker,b"wrong marker");self.rejected(self.enroll)
        self.source.chmod(0o400);self.rejected(self.enroll);self.assertEqual(self.source.stat().st_mode&0o777,0o400)

    def test_bad_historical_types_unknown_schema_and_empty_history_refused(self):
        with closing(sqlite3.connect(self.source)) as db, db:db.execute("UPDATE device_nonces SET signed_at='invalid'")
        self.rejected(self.enroll)

    def test_enrollment_never_overwrites_or_resets(self):
        c=self.enroll();before=c.state();self.rejected(self.enroll);self.assertEqual(before,c.state())

    def test_frozen_requests_rejected_and_preparation_requires_checkpoint(self):
        c=self.enroll();self.rejected(lambda:c.admission().__enter__())
        with patch.object(c,"state",return_value={**c.state(),"checkpoint":None}):self.rejected(lambda:c.prepare("x"))

    def test_freeze_drains_request_and_rejects_new_admission(self):
        c=self.ready();entered=threading.Event();release=threading.Event()
        def request():
            with c.admission():entered.set();release.wait(5)
        with ThreadPoolExecutor() as pool:
            future=pool.submit(request);self.assertTrue(entered.wait(2))
            self.rejected(lambda:c.freeze(timeout=0)) # FROZEN persisted; draining not complete yet.
            self.assertIsNone(c.state()["checkpoint"])
            self.rejected(lambda:c.prepare("must-not-start"));self.rejected(lambda:c.admission().__enter__())
            release.set();future.result(timeout=3)
        c.freeze();self.assertIsNotNone(c.state()["checkpoint"])

    def test_gate_lock_replacement_refuses_migration(self):
        c=self.enroll();lock=self.control/"gate.lock";lock.rename(self.control/"old-gate")
        lc.private_new(lock,b"replacement");self.rejected(lambda:c.prepare("x"))

    def test_missing_admin_lock_never_recreated(self):
        c=self.enroll();(self.control/"admin.lock").unlink();self.rejected(lambda:c.prepare("x"));self.assertFalse((self.control/"admin.lock").exists())

    def test_late_unmanaged_source_write_refused(self):
        c=self.enroll()
        with closing(sqlite3.connect(self.source)) as db, db:db.execute("INSERT INTO device_nonces VALUES ('fixture',?,1,1)",("f"*32,))
        self.rejected(lambda:c.prepare("x"));self.assertFalse((self.control/"x").exists())

    def test_interruption_after_copying_requires_explicit_frozen_recovery(self):
        c=self.enroll()
        with patch.object(lc,"private_new",side_effect=OSError("synthetic disk fault")):self.rejected(lambda:c.prepare("x"))
        self.assertEqual(c.state()["phase"],"FROZEN")
        # Fail after COPYING became durable, leaving incomplete candidate.
        actual=lc.private_new
        def fail_marker(path,data):
            if str(path).endswith(".initializing"):raise OSError("synthetic failure")
            return actual(path,data)
        with patch.object(lc,"private_new",fail_marker):self.rejected(lambda:c.prepare("partial"))
        self.assertEqual(c.state()["phase"],"COPYING");self.rejected(c.resume)
        c.recover();self.assertEqual(c.state()["phase"],"FROZEN")
        self.rejected(lambda:c.prepare("partial"));c.prepare("new-attempt")

    def test_crash_before_state_publication_orphan_event_not_success(self):
        c=self.enroll()
        with patch.object(lc,"atomic_json",side_effect=OSError("synthetic interruption")):self.rejected(lambda:c.prepare("orphan"))
        self.assertEqual(c.state()["phase"],"FROZEN");c.prepare("next")

    def test_partial_marker_and_cross_generation_mismatch_block_switch(self):
        c=self.enroll();c.prepare("x");target=Path(c.state()["candidate"])
        marker=target.with_name(target.name+".initialized");marker.write_bytes(b'{"format":')
        with self.assertRaises(Exception):c.switch()
        self.assertEqual(c.state()["phase"],"VERIFIED");self.rejected(c.resume)

    def test_repeat_prepare_switch_and_resume_refused_without_history_loss(self):
        c=self.enroll();c.prepare("v2");self.rejected(lambda:c.prepare("v2"));c.switch();self.rejected(c.switch)
        c.resume();self.rejected(c.resume);self.assertEqual(len(self.rows(Path(c.state()["active"]))),20)

    def test_concurrent_switch_only_one_publishes(self):
        c=self.enroll();c.prepare("v2")
        def attempt(_):
            try:c.switch();return True
            except (lc.ControlError,OSError):return False
        with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(attempt,range(8)))
        self.assertEqual(sum(results),1);self.assertEqual(c.state()["phase"],"SWITCHED")

    def test_old_backup_missing_later_nonce_rejected(self):
        c=self.ready();target=Path(c.state()["active"]);backup=self.root/"backup.db"
        lc.private_new(backup,b"")
        with lc.sql(target) as src,lc.sql(backup,"rw",allow_empty=True) as dst:src.backup(dst)
        lc.private_new(backup.with_name(backup.name+".initialized"),target.with_name(target.name+".initialized").read_bytes())
        with write_lease(c) as path:NonceStore(path).reserve("fixture","f"*32,int(time.time()),int(time.time()))
        c.freeze();self.rejected(lambda:c.prepare("restore-old",backup=backup))
        self.assertEqual(c.state()["phase"],"COPYING");self.assertEqual(len(self.rows(target)),21)

    def test_missing_authoritative_source_forbids_restore(self):
        c=self.ready();Path(c.state()["active"]).unlink();self.rejected(c.freeze)
        self.rejected(lambda:c.prepare("not-a-new-ledger"));self.assertIsNone(c.state()["checkpoint"])

    def test_crashed_preparation_process_retains_original(self):
        c=self.enroll();code='''import sys,os
from backend import ledger_control as m
c=m.Controller(sys.argv[1]);original=m.private_new
def fail(path,data):
 if str(path).endswith('.initializing'):os._exit(73)
 return original(path,data)
m.private_new=fail;c.prepare('killed')
'''
        child=checked_run([sys.executable,"-B","-c",code,str(self.control)],cwd=Path(__file__).resolve().parents[1],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15)
        self.assertEqual(child.returncode,73);self.assertEqual(c.state()["phase"],"COPYING")
        c.recover();self.assertEqual(len(self.rows(self.source)),20)

    def test_managed_https_asgi_authentication_and_freeze(self):
        c=self.ready();registry=self.root/"fixture-registry.json";write_registry(registry)
        received=[]
        def receiver(payload=Depends(authenticated_sensor_payload)):
            received.append(payload);return {"status":"ok"}
        app=create_app(self.control,registry,receiver=receiver)
        body=b'{"device_id":"esp32-test","object_temp_c":36.5}'
        with TestClient(app,base_url="https://testserver") as client:
            headers=signed_headers(body)
            self.assertEqual(client.post("/sensor-data",content=body,headers=headers).status_code,200)
            self.assertEqual(client.post("/sensor-data",content=body,headers=headers).status_code,409)
            c.freeze()
            self.assertEqual(client.post("/sensor-data",content=body,headers=signed_headers(body)).status_code,503)
            self.assertEqual(client.get("/health").status_code,503);self.assertEqual(len(received),1)

    def test_freeze_waits_and_checkpoint_includes_last_inflight_nonce(self):
        c=self.ready();entered=threading.Event();release=threading.Event()
        def request():
            with write_lease(c) as path:
                entered.set();release.wait(4)
                NonceStore(path).reserve("fixture","f"*32,int(time.time()),int(time.time()))
        with ThreadPoolExecutor() as pool:
            request_future=pool.submit(request);self.assertTrue(entered.wait(2))
            frozen=pool.submit(c.freeze,timeout=3)
            deadline=time.monotonic()+2
            while c.state()["phase"]!="FROZEN" and time.monotonic()<deadline:time.sleep(0.01)
            self.rejected(lambda:c.admission().__enter__());self.assertFalse(frozen.done())
            release.set();request_future.result(timeout=2)
            self.assertEqual(frozen.result(timeout=2)["checkpoint"]["count"],21)

    def test_checkpoint_permission_and_inventory_tamper_refused(self):
        c=self.enroll();self.inventory.write_text('{}');self.rejected(lambda:c.prepare("x"))
        self.assertFalse((self.control/"x").exists())

    def test_empty_history_refused_even_with_matching_receipt(self):
        with closing(sqlite3.connect(self.source)) as db, db:db.execute("DELETE FROM device_nonces")
        self.inventory.write_text(json.dumps({**self.receipt,"checkpoint":lc.fingerprint([])}))
        self.rejected(self.enroll)

    def test_unknown_source_schema_refused(self):
        with closing(sqlite3.connect(self.source)) as db, db:db.execute("CREATE TABLE unexpected (value TEXT)")
        self.rejected(self.enroll)

    def test_corrupt_input_refused_without_repair(self):
        self.source.write_bytes(b'corrupt fixture'*100);self.rejected(self.enroll)
        self.assertEqual(self.source.read_bytes(),b'corrupt fixture'*100)

    def test_partially_replaced_database_blocks_switch(self):
        c=self.enroll();c.prepare("v2");path=Path(c.state()["candidate"])
        path.write_bytes(self.source.read_bytes());self.rejected(c.switch)
        self.assertEqual(c.state()["phase"],"VERIFIED")

    def test_candidate_readonly_does_not_change_permissions_or_enable(self):
        c=self.enroll();c.prepare("v2");target=Path(c.state()["candidate"]);target.chmod(0o400)
        self.rejected(c.switch);self.assertEqual(target.stat().st_mode&0o777,0o400)

    def test_crashed_switch_publishes_no_active_admission(self):
        c=self.enroll();c.prepare("v2")
        actual=lc.atomic_json
        def failed(path,data):
            if data["phase"]=="SWITCHED":raise OSError("synthetic crash")
            actual(path,data)
        with patch.object(lc,"atomic_json",failed):self.rejected(c.switch)
        self.assertEqual(c.state()["phase"],"VERIFIED");self.rejected(lambda:c.admission().__enter__())
        c.switch();c.recover();self.assertEqual(c.state()["phase"],"FROZEN")

    def test_switch_then_restart_controller_does_not_resume_automatically(self):
        c=self.enroll();c.prepare("v2");c.switch();restarted=lc.Controller(self.control)
        self.rejected(lambda:restarted.admission().__enter__());restarted.resume()
        with restarted.admission():pass

    def test_latest_complete_backup_restores_without_losing_new_nonce(self):
        c=self.ready();target=Path(c.state()["active"])
        with write_lease(c) as path:NonceStore(path).reserve("fixture","f"*32,int(time.time()),int(time.time()))
        c.freeze()
        # An explicit backup must be an independent snapshot, not the authority.
        backup=self.root/"latest-independent.db";lc.private_new(backup,b"")
        with lc.sql(target) as src,lc.sql(backup,"rw",allow_empty=True) as dst:src.backup(dst)
        lc.private_new(backup.with_name(backup.name+".initialized"),target.with_name(target.name+".initialized").read_bytes())
        c.verify_backup(backup);c.prepare("restore-latest",backup=backup);c.switch();c.resume()
        with write_lease(c) as path:
            with self.assertRaises(DeviceAuthError) as err:NonceStore(path).reserve("fixture","f"*32,int(time.time()),int(time.time()))
        self.assertEqual(err.exception.status,409)

    def test_cross_process_admission_is_counted_by_freeze(self):
        c=self.ready();code='''import sys,time
from backend.ledger_control import Controller
with Controller(sys.argv[1]).admission():
 print('READY',flush=True);sys.stdin.readline()
'''
        child=start_process([sys.executable,"-B","-c",code,str(self.control)],cwd=Path(__file__).resolve().parents[1],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        self.addCleanup(reap_process,child)
        try:
            self.assertEqual(child.stdout.readline().strip(),'READY');self.rejected(lambda:c.freeze(timeout=0))
            self.rejected(lambda:c.prepare("no-drain"));child.communicate('\n',timeout=5)
            c.freeze();self.assertEqual(c.state()["checkpoint"]["count"],20)
        finally:
            if child.poll() is None:child.kill();child.communicate(timeout=5)

    def test_entire_asgi_handler_is_drained_before_freeze_completes(self):
        c=self.ready();registry=self.root/"test-devices.json";write_registry(registry)
        entered=threading.Event();release=threading.Event();writes=[]
        def receiver(payload=Depends(authenticated_sensor_payload)):
            entered.set();release.wait(4);writes.append(payload);return {"status":"ok"}
        app=create_app(self.control,registry,receiver=receiver)
        body=b'{"device_id":"esp32-test","object_temp_c":36.5}'
        with TestClient(app,base_url="https://testserver") as client,ThreadPoolExecutor() as pool:
            request=pool.submit(client.post,"/sensor-data",content=body,headers=signed_headers(body))
            self.assertTrue(entered.wait(2));freeze=pool.submit(c.freeze,timeout=3)
            deadline=time.monotonic()+2
            while c.state()["phase"]!="FROZEN" and time.monotonic()<deadline:time.sleep(0.01)
            self.assertEqual(client.post("/sensor-data",content=body,headers=signed_headers(body)).status_code,503)
            self.assertFalse(freeze.done());release.set()
            self.assertEqual(request.result(timeout=3).status_code,200)
            self.assertEqual(freeze.result(timeout=3)["checkpoint"]["count"],21)
            self.assertEqual(len(writes),1)

    def test_failed_authentication_and_http_are_not_admitted_to_receiver(self):
        c=self.ready();registry=self.root/"test-devices.json";write_registry(registry)
        writes=[]
        def receiver(payload=Depends(authenticated_sensor_payload)):writes.append(payload);return {}
        app=create_app(self.control,registry,receiver=receiver)
        body=b'{"device_id":"esp32-test","object_temp_c":36.5}'
        with TestClient(app,base_url="https://testserver") as client:
            for field in ("X-CareLink-Api-Key","X-CareLink-Signature"):
                headers=signed_headers(body);headers[field]="0"*64
                self.assertEqual(client.post("/sensor-data",content=body,headers=headers).status_code,401)
        with TestClient(app,base_url="http://testserver") as client:
            self.assertEqual(client.post("/sensor-data",content=body,headers=signed_headers(body)).status_code,426)
        self.assertEqual(writes,[])

    def test_duplicate_json_keys_and_outside_generation_pointer_refused(self):
        c=self.enroll();self.inventory.write_text('{"source":1,"source":2}')
        self.rejected(lambda:c.prepare("x"))

    def test_frozen_checkpoint_cannot_be_silently_replaced(self):
        c=self.enroll()
        with closing(sqlite3.connect(self.source)) as db, db:db.execute("DELETE FROM device_nonces")
        self.rejected(c.freeze);self.assertEqual(c.state()["checkpoint"]["count"],20)

    def test_state_publication_process_crash_keeps_admission_closed(self):
        c=self.enroll();c.prepare("v2")
        code='''import sys,os
from backend import ledger_control as m
original=m.atomic_json
def crash(path,data):
 original(path,data)
 if data['phase']=='SWITCHED':os._exit(73)
m.atomic_json=crash;m.Controller(sys.argv[1]).switch()
'''
        child=checked_run([sys.executable,"-B","-c",code,str(self.control)],cwd=Path(__file__).resolve().parents[1],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15)
        self.assertEqual(child.returncode,73);self.assertEqual(c.state()["phase"],"SWITCHED")
        self.rejected(lambda:c.admission().__enter__());c.recover();c.resume()

    def test_cli_failure_does_not_output_paths_or_authentication_material(self):
        script=Path(__file__).resolve().parents[1]/"scripts/manage-nonce-migration.py"
        child=checked_run([sys.executable,"-B",str(script),"--control-root",str(self.control),"status"],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=10)
        self.assertEqual(child.returncode,1);self.assertEqual(child.stderr,"")
        self.assertNotIn(str(self.root),child.stdout);self.assertNotIn("Traceback",child.stdout)
