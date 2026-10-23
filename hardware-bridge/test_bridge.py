"""Exercise the copied bridge in process; never write to a running device bridge."""
import json
import unittest

import main


async def request(method, path, payload=None, headers=()):
    body = b"" if payload is None else json.dumps(payload).encode()
    messages = []

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        messages.append(message)

    await main.app(
        {
            "type": "http", "asgi": {"version": "3.0"},
            "http_version": "1.1", "method": method, "scheme": "http",
            "path": path, "raw_path": path.encode(), "query_string": b"",
            "headers": [(b"content-type", b"application/json"), *headers],
            "client": ("127.0.0.1", 12345), "server": ("testserver", 80),
        },
        receive, send,
    )
    start = next(m for m in messages if m["type"] == "http.response.start")
    data = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    return start["status"], dict(start["headers"]), data


class BridgeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        main.latest_payload = None
        main.latest_received_at = None

    async def test_health(self):
        status, _, body = await request("GET", "/health")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["service"], "carelink-sensor-bridge")

    async def test_initial_latest_is_expected_503(self):
        status, _, body = await request("GET", "/sensor-data/latest")
        self.assertEqual(status, 503)
        self.assertEqual(json.loads(body)["detail"], "No sensor data received yet")

    async def test_latest_round_trip_and_replacement(self):
        for value in (1.0, 1.2):
            payload = {"device_id": "test-only", "accel_total_g": value, "mpu6050_ok": True}
            status, _, body = await request("POST", "/sensor-data", payload)
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)["device_id"], "test-only")
            status, _, body = await request("GET", "/sensor-data/latest")
            latest = json.loads(body)
            self.assertEqual(status, 200)
            self.assertEqual(latest["data"], payload)
            self.assertIsNotNone(latest["received_at"])

    async def test_non_object_payload_rejected(self):
        status, _, _ = await request("POST", "/sensor-data", ["not an object"])
        self.assertEqual(status, 422)
        self.assertIsNone(main.latest_payload)

    async def test_allowed_origin_preflight(self):
        status, headers, _ = await request("OPTIONS", "/sensor-data", headers=[
            (b"origin", b"http://127.0.0.1:5173"),
            (b"access-control-request-method", b"POST"),
        ])
        self.assertEqual(status, 200)
        self.assertEqual(headers[b"access-control-allow-origin"], b"http://127.0.0.1:5173")

    async def test_unknown_origin_not_granted_browser_access(self):
        status, headers, _ = await request("OPTIONS", "/sensor-data", headers=[
            (b"origin", b"https://untrusted.example"),
            (b"access-control-request-method", b"POST"),
        ])
        self.assertEqual(status, 400)
        self.assertNotIn(b"access-control-allow-origin", headers)


if __name__ == "__main__":
    unittest.main()
