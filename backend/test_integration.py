from pathlib import Path
import json
import tempfile
import unittest
from backend.test_support import AccountClient as TestClient
from backend.security import COOKIE
from backend import app as api

FIXTURES = Path(__file__).resolve().parents[1] / 'sensor_core/tests/fixtures'
class IntegratedMonitoringTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous = api.DATABASE_PATH
        api.DATABASE_PATH = Path(self.temp.name) / 'integration.db'
        self.client = TestClient(api.app)
        self.client.__enter__()
        token=api._create_session_token('wyn')
        self.client.cookies.set(COOKIE, token)
        self.client.headers['X-CSRF-Token']=api.security.csrf(token)
    def tearDown(self):
        self.client.__exit__(None,None,None)
        api.DATABASE_PATH = self.previous
        self.temp.cleanup()
    def post(self, **changes):
        payload = dict(device_id='integration-test',source='synthetic',heart_rate_bpm=75,object_temp_c=36.6,fall_detected=False)
        payload.update(changes)
        response=self.client.post('/sensor-data',json=payload)
        self.assertEqual(response.status_code,200)
        return response.json()
    def latest(self):return self.client.get('/api/patients/ttj').json()['reading']
    def window(self):return json.loads((FIXTURES/'sisfall_fall.json').read_text())['motion_window']
    def test_cnn_real_weights_raise_warning_and_preserve_evidence(self):
        result=self.post(motion_window=self.window(),uptime_ms=3000)
        self.assertEqual(result['label'],'warning')
        self.assertGreater(result['cnn_fall']['fall_probability'],.85)
        self.assertEqual(result['confidence_kind'],'cnn_fall_score')
        reading=self.latest()
        self.assertFalse(reading['fall']['active'])
        self.assertEqual(reading['assessment']['level'],'yellow')
        self.assertIn('CNN fall score',reading['ai']['confidenceMeaning'])
        with api.connect() as db:
            raw=json.loads(db.execute('SELECT raw_json FROM readings').fetchone()[0])
            self.assertNotIn('motion_window',raw)
    def test_cnn_cannot_downgrade_critical(self):
        result=self.post(heart_rate_bpm=140,motion_window=self.window(),uptime_ms=3000)
        self.assertEqual(result['label'],'critical')
        self.assertEqual(result['confidence_kind'],'rule_indicator')
        self.assertIn('not a learned probability',self.latest()['ai']['confidenceMeaning'])
    def test_missing_heart_still_allows_cnn_warning(self):
        self.assertEqual(self.post(heart_rate_bpm=None,motion_window=self.window(),uptime_ms=3000)['label'],'warning')
    def test_held_value_is_display_only_never_a_normal_classification(self):
        self.post(heart_rate_bpm=None,heart_rate_display_bpm=76,heart_rate_held=True,heart_rate_ok=False,heart_rate_last_valid_age_ms=5000)
        r=self.latest()
        self.assertIsNone(r['metrics']['hr']['value'])
        self.assertEqual(r['metrics']['hr']['displayValue'],76)
        self.assertTrue(r['metrics']['hr']['held'])
        self.assertEqual(r['assessment']['level'],'unknown')
        self.assertEqual(r['ai']['state'],'unavailable')
    def test_retained_display_value_expires(self):
        self.post(heart_rate_bpm=None,heart_rate_display_bpm=76,heart_rate_held=True,heart_rate_last_valid_age_ms=31000)
        self.assertIsNone(self.latest()['metrics']['hr']['displayValue'])
    def test_flagged_or_stale_values_are_not_sent_to_lr(self):
        for data in [dict(heart_rate_ok=False),dict(heart_rate_last_valid_age_ms=3001),dict(mlx90614_ok=False)]:
            with self.subTest(data=data):self.assertIsNone(self.post(**data)['label'])
    def test_confirmed_fall_overrides_missing_vitals(self):
        self.assertEqual(self.post(heart_rate_bpm=None,object_temp_c=None,fall_detected=True)['label'],'critical')
    def test_unauthorized_and_cross_patient_requests_are_rejected(self):
        unauth=TestClient(api.app)
        self.assertEqual(unauth.get('/api/patients').status_code,401)
        self.assertEqual(unauth.post('/api/classify',json=dict(heart_rate=75,temperature=36.6,fall=False)).status_code,401)
        self.assertEqual(self.client.get('/api/patients/other/readings').status_code,403)
    def test_invalid_missing_data_and_alert_dedup_recovery(self):
        self.post(heart_rate_bpm=140)
        self.post(heart_rate_bpm=None)
        self.post(heart_rate_bpm=None)
        alerts=self.client.get('/api/alerts').json()
        self.assertEqual(len([a for a in alerts if a['type']=='missing_data' and a['conditionActive']]),1)
        self.assertTrue(any(a['type']=='classification' and a['conditionActive'] for a in alerts))
        self.post()
        self.assertTrue(all(not a['conditionActive'] for a in self.client.get('/api/alerts').json()))
    def test_saved_history_and_synthetic_provenance(self):
        self.post(heart_rate_beat_at_ms=4000,heart_rate_last_valid_age_ms=500,heart_sample_count=2000,heart_sampling_gap_count=0)
        self.assertEqual(self.latest()['source'],'backend')
        self.assertEqual(self.latest()['metrics']['hr']['sampleId'],'integration-test:4000')
        self.assertEqual(len(self.client.get('/api/patients/ttj/readings?minutes=10').json()),1)
        self.assertNotIn('spo2',self.latest()['metrics'])
    def test_untrusted_cnn_outputs_cannot_generate_alert(self):
        r=self.post(cnn_fall={'suspected_fall':True,'fall_probability':1},server_decision={'classification':'critical'})
        self.assertEqual(r['label'],'normal')
        self.assertEqual(r['cnn_fall']['status'],'waiting_for_window')
    def test_patient_cannot_read_other_patient_or_acknowledge(self):
        self.post(heart_rate_bpm=140)
        alert=self.client.get('/api/alerts').json()[0]
        self.client.cookies.clear()
        token=api._create_session_token('ttj')
        self.client.cookies.set(COOKIE,token)
        self.client.headers['X-CSRF-Token']=api.security.csrf(token)
        self.assertEqual(self.client.get('/api/patients/other').status_code,403)
        self.assertEqual(self.client.post('/api/alerts/'+alert['id']+'/acknowledgement').status_code,403)

if __name__=='__main__':unittest.main(verbosity=2)
