"""Storage scope/freeze regression; all files are newly generated fixtures."""
from contextlib import closing
import importlib,json,os,sqlite3,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from .device_auth_test_support import fixture_web_config,write_registry,signed_headers
from .ledger_control import Controller,sql,private_new
from .nonce_ledger import NonceStore
from .web_auth import AuthStore,hash_password
from .write_gate import write_lease

REHEARSALS=[]

class RemediationWriterTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='carelink-writer-scope-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.data=self.root/'readings.db';self.auth=self.root/'auth/web.sqlite3';self.ledger=self.root/'auth/nonces.sqlite3'
        env=fixture_web_config(self.root);env.update(CARELINK_DATABASE_PATH=str(self.data),CARELINK_DEVICE_NONCE_DB=str(self.ledger),CARELINK_DEVICE_REGISTRY=str(self.root/'devices.json'))
        write_registry(self.root/'devices.json');self.env=patch.dict(os.environ,env);self.env.start();self.addCleanup(self.env.stop)
        self.core=importlib.import_module('backend.app');p=patch.object(self.core,'DATABASE_PATH',self.data);p.start();self.addCleanup(p.stop)
        self.c=Controller(env['CARELINK_LEDGER_CONTROL_ROOT'])
        self.client=TestClient(self.core.app,base_url='https://testserver');self.client.__enter__();self.addCleanup(self.client.__exit__,None,None,None)
    def count(self,path,table):
        with closing(sqlite3.connect(Path(path).as_uri()+'?mode=ro',uri=True)) as db:return db.execute('SELECT count(*) FROM '+table).fetchone()[0]
    def test_readings_cannot_alias_ledger_before_schema_initialization(self):
        with patch.object(self.core,'DATABASE_PATH',self.ledger):
            with self.assertRaises(RuntimeError):self.core.initialize_database()
        with sql(self.ledger) as db:self.assertFalse(db.execute("SELECT 1 FROM sqlite_master WHERE name='readings'").fetchone())
    def test_readings_cannot_alias_auth_store(self):
        with patch.object(self.core,'DATABASE_PATH',self.auth):
            with self.assertRaises(RuntimeError):self.core.initialize_database()
        with AuthStore(self.auth).connect() as db:self.assertFalse(db.execute("SELECT 1 FROM sqlite_master WHERE name='readings'").fetchone())
    def test_auth_cannot_alias_switched_ledger_with_stale_environment(self):
        self.c.freeze();self.c.prepare('next');self.c.switch();self.c.resume()
        target=Path(self.c.state()['active'])
        with self.assertRaises(RuntimeError):AuthStore(target)
        self.assertEqual(NonceStore(target).path,target)
    def test_auth_cannot_alias_original_source_after_multiple_switches_and_config_update(self):
        original=self.ledger
        for name in ('first','second'):
            self.c.freeze();self.c.prepare(name);self.c.switch();self.c.resume()
        with patch.dict(os.environ,{'CARELINK_DEVICE_NONCE_DB':str(self.root/'unused.db')}):
            with self.assertRaises(RuntimeError):AuthStore(original)

    def test_sidecar_alias_and_control_artifact_overlap_refused(self):
        from .storage_paths import validate_storage_paths
        for selected in [str(self.ledger)+'-wal',str(self.ledger)+'.initialized',str(self.c.root/'state.json')]:
            with self.assertRaises(RuntimeError):validate_storage_paths(auth=selected)
    def test_missing_readings_database_not_silently_recreated_by_runtime_connection(self):
        missing=self.root/'missing.db'
        with patch.object(self.core,'DATABASE_PATH',missing):
            with self.assertRaises(sqlite3.Error):self.core.connect()
        self.assertFalse(missing.exists())
    def test_frozen_device_domain_blocks_alerts_and_ingress_but_auth_stays_independent(self):
        before=self.count(self.data,'readings');nonces=self.count(self.ledger,'device_nonces')
        self.c.freeze();headers={'Origin':'https://testserver','X-CareLink-CSRF':'1'}
        login=self.client.post('/api/login',headers=headers,json={'username':'wyn','password':'fixture-wyn-password-ONLY'})
        self.assertEqual(login.status_code,200)
        self.assertEqual(self.client.get('/api/session').status_code,200)
        self.assertEqual(self.client.get('/api/alerts').status_code,503)
        body=b'{"device_id":"esp32-test","object_temp_c":36.5}'
        self.assertEqual(self.client.post('/sensor-data',content=body,headers=signed_headers(body)).status_code,503)
        self.assertEqual(self.client.post('/api/logout',headers=headers,json={}).status_code,200)
        self.assertEqual(self.client.get('/api/session').status_code,401)
        self.assertEqual(self.count(self.data,'readings'),before);self.assertEqual(self.count(self.ledger,'device_nonces'),nonces)
        with AuthStore(self.auth).connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM sessions WHERE revoked_at IS NOT NULL').fetchone()[0],1)
            self.assertGreater(db.execute('SELECT count(*) FROM login_limits').fetchone()[0],0)
    def test_auth_backup_restore_requires_latest_revocation_state(self):
        # Synthetic accounts only: prove why old AUTH snapshots must not serve.
        headers={'Origin':'https://testserver','X-CareLink-CSRF':'1'}
        self.assertEqual(self.client.post('/api/login',headers=headers,json={'username':'wyn','password':'fixture-wyn-password-ONLY'}).status_code,200)
        token=self.client.cookies.get('carelink_session');self.assertIsNotNone(token)
        def snapshot(name):
            path=self.root/name;private_new(path,b'')
            with AuthStore(self.auth).connect() as source,closing(sqlite3.connect(path)) as target:
                source.backup(target)
            private_new(path.with_suffix(path.suffix+'.initialized'),b'')
            return path
        stale=snapshot('before-revocation.sqlite3')
        self.assertEqual(self.client.post('/api/logout',headers=headers,json={}).status_code,200)
        latest=snapshot('after-revocation.sqlite3')
        for path,expected in [(latest,401),(stale,200)]:
            with patch.dict(os.environ,{'CARELINK_AUTH_DATABASE_PATH':str(path)}):
                with TestClient(self.core.app,base_url='https://testserver') as restored:
                    status=restored.get('/api/session',headers={'Cookie':'carelink_session='+token}).status_code
            self.assertEqual(status,expected)
            REHEARSALS.append({'operation':'restore synthetic auth '+('latest revoked snapshot' if expected==401 else 'stale snapshot UNSAFE diagnostic'),
                'expected_http':expected,'actual_http':status,'production_restore_allowed':False})
        self.assertIsNone(AuthStore(self.auth).username(token))


class RecoveryEvidenceTests(unittest.TestCase):
    def setUp(self):
        from .device_auth_test_support import fixture_device_control
        self.tmp=tempfile.TemporaryDirectory(prefix='carelink-backup-evidence-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);cfg=fixture_device_control(self.root)
        self.c=Controller(cfg['CARELINK_LEDGER_CONTROL_ROOT']);self.source=Path(self.c.state()['active'])
        self.backup=self.root/'backup.db'
    def snapshot(self):
        self.c.freeze()
        private_new(self.backup,b'')
        with sql(self.source) as source,sql(self.backup,'rw',allow_empty=True) as target:source.backup(target)
        private_new(Path(str(self.backup)+'.initialized'),Path(str(self.source)+'.initialized').read_bytes())
    def rejected(self,call):
        from .ledger_control import ControlError
        from .device_auth_errors import DeviceAuthError
        with self.assertRaises((ControlError,DeviceAuthError,sqlite3.Error,OSError)):call()
    def test_complete_frozen_backup_verification_preserves_every_historical_value(self):
        from .ledger_control import history
        self.snapshot()
        with sql(self.source) as db:before=history(db)
        result=self.c.verify_backup(self.backup)
        self.assertEqual(result['backup_records'],len(before));self.assertEqual(result['phase'],'FROZEN')
        with sql(self.source) as db:self.assertEqual(history(db),before)
        with sql(self.backup) as db:self.assertEqual(history(db),before)
    def test_self_backup_and_aliases_rejected_before_sqlite_open(self):
        from unittest.mock import patch
        from .ledger_control import ControlError
        self.snapshot()
        before=self.source.read_bytes();state=self.c.state()
        directory=self.root/'alias-dir';directory.symlink_to(self.source.parent,target_is_directory=True)
        symlink=self.root/'alias.db';symlink.symlink_to(self.source)
        hardlink=self.root/'hardlink.db';os.link(self.source,hardlink)
        aliases=[self.source,self.source.parent/'.'/self.source.name,
                 directory/self.source.name,symlink,hardlink]
        for alias in aliases:
            with self.subTest(alias=str(alias)),patch('backend.ledger_control.sql',side_effect=AssertionError('SQLite must not open')):
                with self.assertRaises(ControlError):self.c.verify_backup(alias)
        hardlink.unlink()
        self.assertEqual(self.source.read_bytes(),before);self.assertEqual(self.c.state(),state)
        self.assertEqual(self.c.verify_backup(self.backup)['phase'],'FROZEN')

    def test_prepare_explicit_backup_rejects_source_aliases_before_sqlite_or_generation(self):
        from .ledger_control import ControlError
        self.snapshot();state=self.c.state()
        directory=self.root/'prepare-alias-dir';directory.symlink_to(self.source.parent,target_is_directory=True)
        symlink=self.root/'prepare-alias.db';symlink.symlink_to(self.source)
        hardlink=self.root/'prepare-hardlink.db';os.link(self.source,hardlink)
        aliases=[self.source,self.source.parent/'.'/self.source.name,directory/self.source.name,symlink,hardlink]
        try:
            for i,alias in enumerate(aliases):
                with self.subTest(alias=i),patch('backend.ledger_control.sql',side_effect=AssertionError('SQLite must not open')):
                    with self.assertRaises(ControlError):self.c.prepare('reject-self-'+str(i),backup=alias)
                self.assertFalse((self.c.root/('reject-self-'+str(i))).exists())
        finally:hardlink.unlink()
        self.assertEqual(self.c.state(),state)
        self.c.prepare('valid-independent',backup=self.backup)
        self.assertEqual(self.c.state()['phase'],'VERIFIED')

    def test_cli_verification_exit_codes_reject_same_count_tampering(self):
        import sys
        from .process_test_support import checked_run
        from .nonce_ledger import SCHEMA
        self.snapshot()
        command=[sys.executable,str(Path(__file__).resolve().parents[1]/'scripts/manage-nonce-migration.py'),'--control-root',str(self.c.root),'verify-backup','--backup',str(self.backup)]
        good=checked_run(command,capture_output=True,text=True,timeout=10)
        self.assertEqual(good.returncode,0)
        REHEARSALS.append({'operation':'verify complete frozen synthetic backup','initial_phase':'FROZEN','expected_exit':0,'actual_exit':good.returncode,'final_phase':self.c.state()['phase']})
        with sql(self.backup,'rw') as db:
            db.execute('DROP TRIGGER nonce_no_update');db.execute('UPDATE device_nonces SET signed_at=signed_at+1');db.execute(SCHEMA['nonce_no_update'])
        bad=checked_run(command,capture_output=True,text=True,timeout=10)
        self.assertEqual(bad.returncode,1);self.assertNotIn('Traceback',bad.stdout+bad.stderr)
        REHEARSALS.append({'operation':'verify equal-count altered historical values','initial_phase':'FROZEN','expected_exit':1,'actual_exit':bad.returncode,'final_phase':self.c.state()['phase']})
        self.assertEqual(self.c.state()['phase'],'FROZEN')

    def test_verification_requires_freeze_and_drain_checkpoint(self):
        self.rejected(lambda:self.c.verify_backup(self.source))
        with self.c.admission():self.rejected(lambda:self.c.freeze(timeout=0))
        self.assertIsNone(self.c.state()['checkpoint'])
        self.rejected(lambda:self.c.verify_backup(self.source))
    def test_old_backup_missing_later_nonce_never_permits_resume_or_restore(self):
        self.snapshot();self.c.resume()
        with write_lease(self.c) as path:NonceStore(path).reserve('fixture','a'*32,int(time.time()),int(time.time()))
        self.c.freeze();self.rejected(lambda:self.c.verify_backup(self.backup))
        self.assertEqual(self.c.state()['phase'],'FROZEN')
        self.rejected(lambda:self.c.prepare('rejected-old',backup=self.backup))
        with self.assertRaises(Exception):self.c.admission().__enter__()
    def test_equal_counts_with_different_historical_values_are_rejected(self):
        from .nonce_ledger import SCHEMA
        self.snapshot()
        with sql(self.backup,'rw') as db:
            db.execute('DROP TRIGGER nonce_no_update')
            db.execute('UPDATE device_nonces SET accepted_at=accepted_at+1')
            db.execute(SCHEMA['nonce_no_update'])
        self.rejected(lambda:self.c.verify_backup(self.backup))
        self.assertEqual(self.c.state()['phase'],'FROZEN')
    def test_lost_authority_is_not_reconstructed_from_existing_backup(self):
        self.snapshot();self.source.unlink()
        self.rejected(lambda:self.c.verify_backup(self.backup))
        self.assertFalse(self.source.exists());self.assertTrue(self.backup.exists())
    def test_mismatched_marker_or_private_permission_failure_preserves_frozen_state(self):
        self.snapshot();marker=Path(str(self.backup)+'.initialized');original=marker.read_bytes()
        data=json.loads(original);data['ledger_id']='0'*32;marker.write_text(json.dumps(data,sort_keys=True)+'\n')
        self.rejected(lambda:self.c.verify_backup(self.backup))
        marker.write_bytes(original);self.backup.chmod(0o400)
        self.rejected(lambda:self.c.verify_backup(self.backup))
        self.assertEqual(self.backup.stat().st_mode & 0o777,0o400)
    def test_corrupt_truncated_or_unmarked_backup_cannot_change_authority(self):
        self.snapshot();before=self.source.read_bytes();state=self.c.state()
        original=self.backup.read_bytes();marker=Path(str(self.backup)+'.initialized');mark=marker.read_bytes()
        for contents in (b'not a SQLite database',original[:100],b''):
            with self.subTest(kind=len(contents)):
                self.backup.write_bytes(contents)
                self.rejected(lambda:self.c.verify_backup(self.backup))
                self.assertEqual(self.c.state(),state);self.assertEqual(self.source.read_bytes(),before)
        self.backup.write_bytes(original);marker.unlink()
        self.rejected(lambda:self.c.verify_backup(self.backup))
        self.assertEqual(self.c.state(),state);self.assertEqual(self.source.read_bytes(),before)
        private_new(marker,mark)
        self.assertEqual(self.c.verify_backup(self.backup)['phase'],'FROZEN')
    def test_two_admin_processes_cannot_overlap_verification(self):
        import selectors,sys
        from .process_test_support import start_process,reap_process
        self.snapshot()
        code="import sys;from backend.ledger_control import Controller\nwith Controller(sys.argv[1]).admin():\n print('READY',flush=True);sys.stdin.readline()\n"
        child=start_process([sys.executable,'-B','-c',code,str(self.c.root)],cwd=Path(__file__).resolve().parents[1],stdin=-1,stdout=-1,stderr=-1,text=True)
        self.addCleanup(reap_process,child)
        with selectors.DefaultSelector() as selector:
            selector.register(child.stdout,selectors.EVENT_READ)
            self.assertTrue(selector.select(timeout=5));self.assertEqual(child.stdout.readline().strip(),'READY')
        self.rejected(lambda:self.c.verify_backup(self.backup))
        child.communicate('\n',timeout=5);self.assertEqual(child.returncode,0)
        self.assertGreater(self.c.verify_backup(self.backup)['backup_records'],0)
    def test_latest_snapshot_restore_simulation_keeps_replay_history(self):
        from .ledger_control import history
        from .device_auth_errors import DeviceAuthError
        with write_lease(self.c) as path:NonceStore(path).reserve('fixture','b'*32,int(time.time()),int(time.time()))
        self.snapshot();self.c.verify_backup(self.backup)
        with sql(self.source) as db:before=history(db)
        self.c.prepare('restored',backup=self.backup);self.c.switch();self.c.resume()
        restored=Path(self.c.state()['active'])
        with sql(restored) as db:self.assertEqual(history(db),before)
        with write_lease(self.c):
            with self.assertRaises(DeviceAuthError) as error:NonceStore(restored).reserve('fixture','b'*32,int(time.time()),int(time.time()))
            self.assertEqual(error.exception.status,409)

class MaintenancePolicyTests(unittest.TestCase):
    def test_legacy_checker_requires_explicit_root_and_approval_before_any_reads(self):
        import sys
        from .process_test_support import checked_run
        script=Path(__file__).resolve().parents[1]/'scripts/check-device-migration.py'
        result=checked_run([sys.executable,str(script)],capture_output=True,text=True,timeout=5)
        self.assertEqual(result.returncode,2);self.assertNotIn('Traceback',result.stderr)
    def test_legacy_checker_refuses_network_mode_without_probing_services(self):
        import sys
        from .process_test_support import checked_run
        script=Path(__file__).resolve().parents[1]/'scripts/check-device-migration.py'
        with tempfile.TemporaryDirectory(prefix='carelink-checker-no-network-') as directory:
            result=checked_run([sys.executable,str(script),'--config-root',directory,'--confirm-approved-read-only-inspection','--network'],capture_output=True,text=True,timeout=5)
            self.assertEqual(result.returncode,2);self.assertNotIn('Traceback',result.stderr)
            self.assertEqual(list(Path(directory).iterdir()),[])
