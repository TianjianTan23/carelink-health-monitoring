from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient


# No environment or temporary files are changed while unittest discovers modules.
from backend.device_auth_test_support import signing_client
from backend import app as core
from backend.app import app, connect


class CareLinkApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp=tempfile.TemporaryDirectory(prefix="carelink-test-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.env=patch.dict(os.environ,{k:v for k,v in os.environ.items() if not k.startswith("CARELINK_")},clear=True)
        cls.env.start();cls.addClassCleanup(cls.env.stop)
        database=Path(cls.temp.name)/"test.db"
        os.environ["CARELINK_DATABASE_PATH"]=str(database)
        cls.Client=signing_client(TestClient,cls.temp.name)
        cls.database_patch=patch.object(core,"DATABASE_PATH",database)
        cls.database_patch.start();cls.addClassCleanup(cls.database_patch.stop)
        cls.context=cls.Client(app);cls.client=cls.context.__enter__()
        cls.addClassCleanup(cls.context.__exit__,None,None,None)

    def login(self, username: str, password: str) -> TestClient:
        client = self.Client(app)
        client.__enter__()
        response = client.post("/api/login", json={"username": username, "password": password})
        self.assertEqual(response.status_code, 200)
        self.addCleanup(client.__exit__, None, None, None)
        return client

    def test_credentials_determine_role(self) -> None:
        patient = self.login("ttj", "fixture-ttj-password-ONLY")
        nurse = self.login("wyn", "fixture-wyn-password-ONLY")
        self.assertEqual(patient.get("/api/session").json()["role"], "patient")
        self.assertEqual(nurse.get("/api/session").json()["role"], "clinician")
        self.assertEqual(self.client.post("/api/login", json={"username": "ttj", "password": "wrong-synthetic-password"}).status_code, 401)

    def test_model_and_rule_attribution_are_stored_and_returned(self) -> None:
        response = self.client.post("/sensor-data", json={
            "device_id": "esp32-test",
            "heart_rate_bpm": 142,
            "object_temp_c": 40.0,
            "fall_detected": True,
            "accel_x_g": 0.2,
            "accel_y_g": 0.1,
            "accel_z_g": 2.7,
        })
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn(payload["label"], {"normal", "warning", "critical"})
        self.assertEqual(payload["label"], "critical")
        self.assertTrue(payload["actions"]["buzzer"])
        self.assertIsInstance(payload["confidence"], float)
        self.assertEqual({item["parameter"] for item in payload["abnormal_params"]}, {"heart_rate_bpm", "temperature_c", "fall_detected"})

        nurse = self.login("wyn", "fixture-wyn-password-ONLY")
        predictions = nurse.get("/api/patients/ttj/predictions").json()
        self.assertEqual(predictions[0]["result"]["label"], payload["label"])
        self.assertEqual(predictions[0]["confidence"], payload["confidence"])
        readings = nurse.get("/api/patients/ttj/readings?minutes=1440").json()
        self.assertEqual(readings[0]["metrics"]["hr"]["value"], 142.0)
        self.assertNotIn("spo2", readings[0]["metrics"])

    def test_missing_invalid_and_duplicate_unresolved_alerts(self) -> None:
        invalid = {"device_id": "esp32-test", "heart_rate_bpm": 75, "object_temp_c": 24.5, "fall_detected": False}
        first = self.client.post("/sensor-data", json=invalid).json()
        second = self.client.post("/sensor-data", json=invalid).json()
        self.assertIsNone(first["label"])
        self.assertEqual(first["abnormal_params"][0]["kind"], "invalid_reading")
        self.assertIsNone(second["confidence"])
        self.assertFalse(first["actions"]["buzzer"])
        with connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS total, MAX(occurrence_count) AS occurrences FROM alerts WHERE alert_key='invalid_reading:temperature_c' AND status IN ('new','acknowledged')"
            ).fetchone()
        self.assertEqual(row["total"], 1)
        self.assertGreaterEqual(row["occurrences"], 2)

    def test_normal_classification_keeps_buzzer_off(self) -> None:
        response = self.client.post("/sensor-data", json={
            "device_id": "esp32-test",
            "heart_rate_bpm": 76,
            "object_temp_c": 36.7,
            "fall_detected": False,
        })
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["label"], "normal")
        self.assertFalse(payload["actions"]["buzzer"])

    def test_invalid_sensor_flags_override_plausible_values(self) -> None:
        response = self.client.post("/sensor-data", json={
            "device_id": "quality-test", "heart_rate_bpm": 72,
            "heart_rate_ok": False, "object_temp_c": 36.5,
            "mlx90614_ok": False, "fall_detected": False, "mpu6050_ok": False,
        })
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["label"])
        nurse = self.login("wyn", "fixture-wyn-password-ONLY")
        reading = nurse.get("/api/patients/ttj").json()["reading"]
        self.assertIsNone(reading["metrics"]["hr"]["value"])
        self.assertFalse(reading["metrics"]["hr"]["available"])
        self.assertFalse(reading["metrics"]["temp"]["available"])
        self.assertEqual(reading["fall"]["quality"], "unavailable")

    def test_held_heart_rate_is_not_a_new_valid_measurement(self) -> None:
        response = self.client.post("/sensor-data", json={
            "device_id": "quality-test", "heart_rate_bpm": None,
            "heart_rate_display_bpm": 72, "heart_rate_ok": False,
            "heart_rate_held": True, "heart_rate_last_valid_age_ms": 600000,
            "object_temp_c": 36.5, "fall_detected": False,
        })
        self.assertIsNone(response.json()["label"])
        nurse = self.login("wyn", "fixture-wyn-password-ONLY")
        reading = nurse.get("/api/patients/ttj").json()["reading"]
        self.assertIsNone(reading["metrics"]["hr"]["value"])
        self.assertEqual(reading["ai"]["state"], "unavailable")

    def test_surface_temperature_remains_visible_outside_model_domain(self) -> None:
        response = self.client.post("/sensor-data", json={
            "device_id": "quality-test", "heart_rate_bpm": 72,
            "heart_rate_ok": True, "object_temp_c": 25.6,
            "mlx90614_ok": True, "fall_detected": False,
        })
        self.assertIsNone(response.json()["label"])
        self.assertFalse(response.json()["actions"]["buzzer"])
        nurse = self.login("wyn", "fixture-wyn-password-ONLY")
        reading = nurse.get("/api/patients/ttj").json()["reading"]
        self.assertEqual(reading["metrics"]["temp"], {"value": 25.6, "quality": "good", "available": True})
        self.assertEqual(reading["ai"]["state"], "unavailable")
        self.assertEqual(reading["assessment"]["level"], "unknown")

    def test_patient_cannot_acknowledge_but_nurse_can(self) -> None:
        self.client.post("/sensor-data", json={"device_id": "esp32-test", "heart_rate_bpm": 145, "object_temp_c": 40, "fall_detected": True})
        patient = self.login("ttj", "fixture-ttj-password-ONLY")
        nurse = self.login("wyn", "fixture-wyn-password-ONLY")
        active_alerts = [item for item in patient.get("/api/alerts").json() if item["conditionActive"] and item["status"] == "new"]
        alert_id = active_alerts[0]["id"]
        self.assertEqual(patient.post(f"/api/alerts/{alert_id}/acknowledgement").status_code, 403)
        acknowledged = nurse.post(f"/api/alerts/{alert_id}/acknowledgement")
        self.assertEqual(acknowledged.status_code, 200)
        self.assertEqual(acknowledged.json()["status"], "acknowledged")

    def test_network_failure_becomes_stored_alert(self) -> None:
        self.client.post("/sensor-data", json={"device_id": "esp32-test", "heart_rate_bpm": 76, "object_temp_c": 36.7, "fall_detected": False})
        old_time = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        from .write_gate import write_lease
        with write_lease(), connect() as connection:
            connection.execute("UPDATE readings SET created_at=?", (old_time,))
        patient = self.login("ttj", "fixture-ttj-password-ONLY")
        alerts = patient.get("/api/alerts").json()
        self.assertTrue(any(item["type"] == "network_failure" for item in alerts))


if __name__ == "__main__":
    unittest.main()
