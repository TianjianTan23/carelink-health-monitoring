"""Course demo tests: entirely new temporary databases, no live paths."""
import importlib,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from .coursework_demo import prepare,paths,simulator_headers,simulated_payload,install_demo_adapter

class CourseworkDemoTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='carelink-course-demo-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'new';env={**paths(self.root),'CARELINK_WEB_ORIGINS':'https://testserver'}
        self.patch=patch.dict(os.environ,env);self.patch.start();self.addCleanup(self.patch.stop)
        prepare(self.root,initialize=True)
    def test_new_demo_only_and_partial_state_not_recreated(self):
        before=(self.root/'auth/nonces.sqlite3').read_bytes();prepare(self.root)
        self.assertEqual((self.root/'auth/nonces.sqlite3').read_bytes(),before)
        marker=self.root/'auth/nonces.sqlite3.initialized';marker.unlink()
        with self.assertRaises(RuntimeError):prepare(self.root,initialize=True)
        self.assertFalse(marker.exists());self.assertEqual((self.root/'auth/nonces.sqlite3').read_bytes(),before)
    def test_real_routes_accept_signed_simulation_mark_it_mock_and_revoke(self):
        core=importlib.import_module('backend.app');old_routes=list(core.app.router.routes);original=core._reading_from_row
        self.addCleanup(setattr,core.app.router,'routes',old_routes);self.addCleanup(setattr,core,'_reading_from_row',original)
        web=Path(self.tmp.name)/'web';web.mkdir();(web/'index.html').write_text('Coursework simulated')
        with patch.object(core,'DATABASE_PATH',self.root/'data/readings.db'):
            app=install_demo_adapter(core,web)
            with TestClient(app,base_url='https://testserver') as client:
                headers={'Origin':'https://testserver','X-CareLink-CSRF':'1'}
                body=json.dumps(simulated_payload(0)).encode()
                self.assertEqual(client.post('/sensor-data',content=body,headers=simulator_headers(self.root,body)).status_code,200)
                self.assertEqual(client.post('/sensor-data',content=body,headers={'Content-Type':'application/json'}).status_code,401)
                self.assertEqual(client.post('/api/login',headers=headers,json={'username':'demo-clinician','password':'coursework-demo'}).status_code,200)
                reading=client.get('/api/patients').json()[0]['reading'];self.assertEqual(reading['source'],'mock');self.assertEqual(reading['deviceId'],'coursework-simulator')
                old=client.cookies.get('carelink_session');self.assertEqual(client.post('/api/logout',headers=headers,json={}).status_code,200)
                self.assertEqual(client.get('/api/session',headers={'Cookie':'carelink_session='+old}).status_code,401)
    def test_certificate_has_identifiers_and_emulator_identity(self):
        import subprocess
        cert=self.root/'tls/server.crt';r=subprocess.run(['openssl','verify','-CAfile',str(self.root/'tls/root.crt'),'-verify_ip','10.0.2.2',str(cert)],capture_output=True,text=True)
        self.assertEqual(r.returncode,0)
        t=subprocess.check_output(['openssl','x509','-in',str(cert),'-noout','-text'],text=True)
        self.assertIn('Authority Key Identifier',t);self.assertIn('Subject Key Identifier',t)
