"""Stage-by-stage acceptance evidence. Synthetic DBs only, no service ports."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import importlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from .device_auth_test_support import fixture_web_config,write_registry,signed_headers
from .device_auth import DeviceAuthenticator,DeviceAuthError
from .nonce_ledger import NonceStore
from .ledger_control import Controller,ControlError
from .write_gate import write_lease
from .process_test_support import reap_process, start_process, checked_run, child_diagnostic

RESULTS=[]
BODY=b'{"device_id":"esp32-test","heart_rate_bpm":76,"object_temp_c":36.5,"fall_detected":false}'


def count(path,table):
    db=sqlite3.connect(Path(path).as_uri()+"?mode=ro",uri=True)
    try:return db.execute('SELECT count(*) FROM '+table).fetchone()[0]
    finally:db.close()


def exercise(clients,n,headers,case):
    """Instrument boundaries independently; never prints credentials/payloads."""
    from . import app as core
    metrics=Counter();lock=threading.Lock()
    def bump(key):
        with lock:metrics[key]+=1
    verify=DeviceAuthenticator.verify;reserve=NonceStore.reserve;auth=DeviceAuthenticator.authenticate_payload;business=core._extract
    def signed(self,*args,**kwargs):
        result=verify(self,*args,**kwargs);bump('signature_verified');return result
    def occupied(self,*args,**kwargs):
        bump('nonce_attempted')
        try:result=reserve(self,*args,**kwargs)
        except DeviceAuthError as error:bump('nonce_rejected_'+str(error.status));raise
        bump('nonce_committed');return result
    def accepted(self,*args,**kwargs):
        result=auth(self,*args,**kwargs);bump('authentication_accepted');return result
    def operation(*args,**kwargs):bump('business_calls');return business(*args,**kwargs)
    # Concurrency is orthogonal to clock expiry; freeze only this synthetic
    # ASGI batch's clock. Production windows and expiry tests are unchanged.
    with patch('time.time',return_value=int(headers['X-CareLink-Timestamp'])),patch.object(DeviceAuthenticator,'verify',signed),patch.object(NonceStore,'reserve',occupied),patch.object(DeviceAuthenticator,'authenticate_payload',accepted),patch.object(core,'_extract',operation):
        def send(i):return clients[i%len(clients)].post('/sensor-data',content=BODY,headers=headers).status_code
        with ThreadPoolExecutor(max_workers=min(n,32)) as pool:statuses=list(pool.map(send,range(n)))
    return {'case':case,'requests':n,'stages':dict(metrics),'http':dict(Counter(statuses))}


class AtomicFreezeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='carelink-atomic-http-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.nonce=self.root/'auth/nonces.sqlite3';self.data=self.root/'readings.db';self.registry=self.root/'auth/devices.json'
        cfg=fixture_web_config(self.root);write_registry(self.registry)
        cfg.update(CARELINK_DATABASE_PATH=str(self.data),CARELINK_DEVICE_REGISTRY=str(self.registry),CARELINK_DEVICE_NONCE_DB=str(self.nonce))
        self.env=patch.dict(os.environ,cfg);self.env.start();self.addCleanup(self.env.stop)
        self.core=importlib.import_module('backend.app');p=patch.object(self.core,'DATABASE_PATH',self.data);p.start();self.addCleanup(p.stop)
        self.c=Controller(cfg['CARELINK_LEDGER_CONTROL_ROOT'])
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        old=importlib.import_module('backend.device_ingress').app
        from .controlled_device_ingress import create_app
        new=create_app(self.c.root,self.registry)
        self.old=self.stack.enter_context(TestClient(old,base_url='https://testserver'))
        self.new=self.stack.enter_context(TestClient(new,base_url='https://testserver'))

    def run_acceptance(self,n,case):
        before_nonce=count(self.nonce,'device_nonces');before_data=count(self.data,'readings')
        result=exercise([self.old,self.new],n,signed_headers(BODY),case)
        result['nonce_delta']=count(self.nonce,'device_nonces')-before_nonce;result['reading_delta']=count(self.data,'readings')-before_data
        RESULTS.append(result)
        self.assertEqual(result['http'],{200:1,409:n-1})
        for field in ('nonce_committed','authentication_accepted','business_calls'):self.assertEqual(result['stages'][field],1)
        self.assertEqual(result['stages']['signature_verified'],n)
        self.assertEqual(result['stages']['nonce_attempted'],n)
        self.assertEqual(result['nonce_delta'],1);self.assertEqual(result['reading_delta'],1)

    def test_two_simultaneous_old_and_new_requests(self):self.run_acceptance(2,'two-mixed-http')
    def test_32_simultaneous_old_and_new_requests(self):self.run_acceptance(32,'32-mixed-http')
    def test_64_simultaneous_old_and_new_requests(self):self.run_acceptance(64,'64-mixed-http')

    def test_two_processes_32_http_requests(self):
        code='''import sys,json,os
from fastapi.testclient import TestClient
from backend import app as core
from backend.device_ingress import app as old
from backend.controlled_device_ingress import create_app
from backend.test_atomic_freeze import exercise,BODY
from backend.device_auth_test_support import signed_headers
new=create_app(os.environ['CARELINK_LEDGER_CONTROL_ROOT'],os.environ['CARELINK_DEVICE_REGISTRY'])
with TestClient(old,base_url='https://testserver') as a,TestClient(new,base_url='https://testserver') as b:
 h=signed_headers(BODY,nonce='a'*32,timestamp=int(sys.argv[1]))
 print(json.dumps(exercise([a,b],16,h,'process-http')))
'''
        before_nonce=count(self.nonce,'device_nonces');before_data=count(self.data,'readings')
        stamp=str(int(time.time()))
        stages=Counter();statuses=Counter()
        with ExitStack() as processes:
            children=[]
            for _ in range(2):
                child=start_process([sys.executable,'-B','-c',code,stamp],cwd=Path(__file__).resolve().parents[1],env=os.environ.copy(),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                processes.callback(reap_process,child);children.append(child)
            for child in children:
                out,err=child.communicate(timeout=45);self.assertEqual(child.returncode,0,child_diagnostic(err))
                row=json.loads(out);stages.update(row['stages']);statuses.update({int(k):v for k,v in row['http'].items()})
        result={'case':'2-process-32-mixed-http','requests':32,'stages':dict(stages),'http':dict(statuses),'nonce_delta':count(self.nonce,'device_nonces')-before_nonce,'reading_delta':count(self.data,'readings')-before_data};RESULTS.append(result)
        self.assertEqual(statuses,{200:1,409:31})
        for field in ('nonce_committed','authentication_accepted','business_calls'):self.assertEqual(stages[field],1)
        self.assertEqual(stages['signature_verified'],32);self.assertEqual(result['nonce_delta'],1);self.assertEqual(result['reading_delta'],1)

    def test_transaction_commit_failure_has_no_acceptance_or_business(self):
        from . import nonce_ledger
        original=nonce_ledger._sqlite
        class BrokenCommit:
            def __init__(self,db):self.db=db
            def __getattr__(self,name):return getattr(self.db,name)
            def commit(self):
                if self.db.total_changes:raise sqlite3.OperationalError('synthetic commit failure')
                self.db.commit()
        before_nonce=count(self.nonce,'device_nonces');before_data=count(self.data,'readings')
        with patch.object(nonce_ledger,'_sqlite',lambda p:BrokenCommit(original(p))):
            result=exercise([self.old,self.new],2,signed_headers(BODY),'commit-failure')
        result.update(nonce_delta=count(self.nonce,'device_nonces')-before_nonce,reading_delta=count(self.data,'readings')-before_data);RESULTS.append(result)
        self.assertEqual(result['http'],{503:2});self.assertEqual(result['stages']['signature_verified'],2)
        for field in ('nonce_committed','authentication_accepted','business_calls'):self.assertEqual(result['stages'].get(field,0),0)
        self.assertEqual(result['nonce_delta'],0);self.assertEqual(result['reading_delta'],0)

    def test_legacy_base_app_and_new_entry_all_reject_when_frozen(self):
        c=self.stack.enter_context(TestClient(self.core.app,base_url='https://testserver'))
        self.c.freeze();before=count(self.data,'readings');before_nonce=count(self.nonce,'device_nonces')
        result=exercise([self.old,self.new,c],24,signed_headers(BODY),'24-frozen-all-entries');result['reading_delta']=count(self.data,'readings')-before;result['nonce_delta']=count(self.nonce,'device_nonces')-before_nonce;RESULTS.append(result)
        self.assertEqual(result['http'],{503:24});self.assertEqual(result['stages'],{});self.assertEqual(result['reading_delta'],0)

    def test_inflight_old_request_drains_both_entries_block_migration(self):
        entered=threading.Event();release=threading.Event();original=self.core._extract
        verify=DeviceAuthenticator.verify;reserve=NonceStore.reserve;auth=DeviceAuthenticator.authenticate_payload
        metrics=Counter();before_nonce=count(self.nonce,'device_nonces');before_data=count(self.data,'readings')
        def checked(self,*a,**kw):
            result=verify(self,*a,**kw);metrics['signature_verified']+=1;return result
        def occupied(self,*a,**kw):
            metrics['nonce_attempted']+=1;result=reserve(self,*a,**kw);metrics['nonce_committed']+=1;return result
        def accepted(self,*a,**kw):
            result=auth(self,*a,**kw);metrics['authentication_accepted']+=1;return result
        def hold(*a,**kw):
            metrics['business_calls']+=1;entered.set();release.wait(5);return original(*a,**kw)
        with patch.object(self.core,'_extract',hold),patch.object(DeviceAuthenticator,'verify',checked),patch.object(NonceStore,'reserve',occupied),patch.object(DeviceAuthenticator,'authenticate_payload',accepted),ThreadPoolExecutor() as pool:
            request=pool.submit(self.old.post,'/sensor-data',content=BODY,headers=signed_headers(BODY));self.assertTrue(entered.wait(3))
            with self.assertRaises(ControlError):self.c.freeze(timeout=0)
            self.assertIsNone(self.c.state()['checkpoint'])
            with self.assertRaises(ControlError):self.c.prepare('must-not-migrate')
            for client in (self.old,self.new):self.assertEqual(client.post('/sensor-data',content=BODY,headers=signed_headers(BODY)).status_code,503)
            release.set();self.assertEqual(request.result(timeout=5).status_code,200)
        self.c.freeze();self.assertEqual(self.c.state()['checkpoint']['count'],count(self.nonce,'device_nonces'))
        result={'case':'freeze-inflight-old-new','requests':3,'stages':dict(metrics),'http':{200:1,503:2},'nonce_delta':count(self.nonce,'device_nonces')-before_nonce,'reading_delta':count(self.data,'readings')-before_data};RESULTS.append(result)
        for field in ('signature_verified','nonce_attempted','nonce_committed','authentication_accepted','business_calls'):self.assertEqual(metrics[field],1)
        self.assertEqual(result['nonce_delta'],1);self.assertEqual(result['reading_delta'],1)

    def test_missing_gate_denies_legacy_http_and_direct_business(self):
        from fastapi import HTTPException
        with patch.dict(os.environ,{'CARELINK_LEDGER_CONTROL_ROOT':''}):
            self.assertEqual(self.old.post('/sensor-data',content=BODY,headers=signed_headers(BODY)).status_code,503)
            with self.assertRaises(HTTPException):self.core.receive_sensor_data(json.loads(BODY))

    def test_direct_business_rejects_unverified_dict_and_reused_receipt(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as err:self.core.receive_sensor_data(json.loads(BODY))
        self.assertEqual(err.exception.status_code,403)
        a=DeviceAuthenticator(self.registry,self.nonce)
        h={k.lower():v for k,v in signed_headers(BODY).items()}
        with write_lease():
            payload=a.authenticate_payload('POST',b'/sensor-data',b'',h,BODY)
            self.core.receive_sensor_data(payload)
            with self.assertRaises(HTTPException) as err:self.core.receive_sensor_data(payload)
        self.assertEqual(err.exception.status_code,409)

    def test_second_gate_for_same_ledger_refused(self):
        receipt=self.root/'auth/inventory.json';s=self.c.state();self.c.freeze()
        with self.assertRaises(FileExistsError):Controller.enroll(self.root/'second-control',self.nonce,receipt)

    def test_database_connection_denies_ungated_mutation(self):
        with self.core.connect() as db:
            with self.assertRaises(sqlite3.DatabaseError):db.execute('DELETE FROM readings')
            with self.assertRaises(sqlite3.DatabaseError):db.cursor().execute('PRAGMA query_only=OFF')
            with self.assertRaises(sqlite3.DatabaseError):db.execute('-- comment\nPRAGMA query_only=OFF')
        self.c.freeze()
        with self.assertRaises(Exception):self.core.initialize_database()

    def test_process_exit_before_and_after_nonce_commit(self):
        for committed,nonce in ((False,'b'*32),(True,'c'*32)):
            before_child_nonce=count(self.nonce,'device_nonces')
            code='''import sys,os,time
from pathlib import Path
from backend.nonce_ledger import NonceStore
p=Path(sys.argv[1]);nonce=sys.argv[2]
if sys.argv[3]=='yes':
 NonceStore(p).reserve('esp32-test',nonce,int(time.time()),int(time.time()));os._exit(73)
from backend.write_gate import write_lease
with write_lease(),NonceStore(p).connect() as db:
 db.execute('INSERT INTO device_nonces VALUES (?,?,?,?)',('esp32-test',nonce,int(time.time()),int(time.time())));os._exit(73)
'''
            child=checked_run([sys.executable,'-B','-c',code,str(self.nonce),nonce,'yes' if committed else 'no'],cwd=Path(__file__).resolve().parents[1],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20)
            self.assertEqual(child.returncode,73)
            child_nonce_delta=count(self.nonce,'device_nonces')-before_child_nonce
            before_nonce=count(self.nonce,'device_nonces');before=count(self.data,'readings');result=exercise([self.old,self.new],2,signed_headers(BODY,nonce=nonce),'crash-'+('committed' if committed else 'uncommitted'))
            result['reading_delta']=count(self.data,'readings')-before;result['nonce_delta']=count(self.nonce,'device_nonces')-before_nonce;result['child_nonce_delta']=child_nonce_delta;RESULTS.append(result)
            self.assertEqual(result['http'],{409:2} if committed else {200:1,409:1})
            self.assertEqual(result['reading_delta'],0 if committed else 1)

    def test_file_checks_do_not_close_sqlite_or_lock_sidecars(self):
        from . import nonce_ledger as m
        original=os.open
        def safe_open(path,flags,*a,**kw):
            if Path(path) in [self.nonce,self.nonce.with_name(self.nonce.name+'-wal'),self.nonce.with_name(self.nonce.name+'-shm')]:
                raise AssertionError('Raw SQLite descriptor must not be opened by metadata checking')
            return original(path,flags,*a,**kw)
        with patch.object(m.os,'open',safe_open):self.run_acceptance(32,'no-raw-sqlite-fd')

    def test_bound_low_level_reserve_and_connection_obey_freeze(self):
        self.c.freeze();before=count(self.nonce,'device_nonces')
        with self.assertRaises(DeviceAuthError) as err:NonceStore(self.nonce).reserve('esp32-test','d'*32,int(time.time()),int(time.time()))
        self.assertEqual(err.exception.status,503)
        with self.assertRaises(DeviceAuthError):
            with NonceStore(self.nonce).connect() as db:
                db.execute('INSERT INTO device_nonces VALUES (?,?,?,?)',('esp32-test','e'*32,int(time.time()),int(time.time())))
        self.assertEqual(count(self.nonce,'device_nonces'),before)

    def test_old_entries_follow_switched_ledger_not_stale_environment(self):
        self.c.freeze();self.c.prepare('switched');self.c.switch();self.c.resume()
        selected=Path(self.c.state()['active']);self.assertNotEqual(selected,self.nonce)
        before_old=count(self.nonce,'device_nonces');before_new=count(selected,'device_nonces')
        before_data=count(self.data,'readings')
        result=exercise([self.old,self.new],2,signed_headers(BODY),'old-new-after-switch')
        result.update(nonce_delta=count(selected,'device_nonces')-before_new,old_nonce_delta=count(self.nonce,'device_nonces')-before_old,reading_delta=count(self.data,'readings')-before_data);RESULTS.append(result)
        self.assertEqual(result['http'],{200:1,409:1});self.assertEqual(count(self.nonce,'device_nonces'),before_old)
        self.assertEqual(count(selected,'device_nonces')-before_new,1)

    def test_posix_record_lock_survives_metadata_checks(self):
        import fcntl
        from .nonce_ledger import _file
        p=self.root/'record-lock-test';fd=os.open(p,os.O_CREAT|os.O_EXCL|os.O_RDWR,0o600)
        try:
            fcntl.lockf(fd,fcntl.LOCK_EX)
            _file(p)
            code='''import os,sys,fcntl
fd=os.open(sys.argv[1],os.O_RDWR)
try:fcntl.lockf(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);print('UNEXPECTED')
except BlockingIOError:print('BLOCKED')
os.close(fd)
'''
            self.assertEqual(subprocess.check_output([sys.executable,'-c',code,str(p)],text=True).strip(),'BLOCKED')
        finally:os.close(fd)

    def test_business_rejects_receipt_from_a_different_ledger(self):
        from .nonce_ledger import initialize_new_ledger,AUTHORIZATION
        from fastapi import HTTPException
        other=self.root/'other-ledger.db';initialize_new_ledger(other,authorization=AUTHORIZATION)
        h={k.lower():v for k,v in signed_headers(BODY).items()}
        payload=DeviceAuthenticator(self.registry,other).authenticate_payload('POST',b'/sensor-data',b'',h,BODY)
        before=count(self.data,'readings')
        with self.assertRaises(HTTPException) as err:self.core.receive_sensor_data(payload)
        self.assertEqual(err.exception.status_code,403);self.assertEqual(count(self.data,'readings'),before)

    def test_prepared_mutation_cannot_retain_permission_after_lease(self):
        with write_lease():
            db=self.core.connect()
            with db:db.execute('UPDATE readings SET created_at=created_at')
        try:
            self.c.freeze()
            with self.assertRaises(sqlite3.DatabaseError):db.execute('UPDATE readings SET created_at=created_at')
        finally:db.close()

    def test_execute_returned_cursor_cannot_disable_read_only(self):
        before=count(self.data,'readings')
        with self.core.connect() as db:
            cursor=db.execute('SELECT count(*) FROM readings')
            with self.assertRaises(sqlite3.DatabaseError):cursor.execute('PRAGMA query_only=OFF')
            with self.assertRaises(sqlite3.DatabaseError):cursor.executescript('DELETE FROM readings;')
        self.assertEqual(count(self.data,'readings'),before)

    def test_execute_returned_cursor_cannot_write_after_lease_or_freeze(self):
        with write_lease():
            db=self.core.connect()
            cursor=db.execute('SELECT count(*) FROM readings')
        try:
            self.c.freeze()
            with self.assertRaises(sqlite3.DatabaseError):cursor.execute('UPDATE readings SET created_at=created_at')
            with self.assertRaises(sqlite3.DatabaseError):cursor.execute('COMMIT')
        finally:db.close()
