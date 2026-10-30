"""Fail-closed per-device authentication; no credentials are ever logged."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import stat
import time
import threading
from typing import Any, Mapping

from fastapi import HTTPException, Request
from starlette.concurrency import run_in_threadpool
from .device_diagnostics import event

VERSION = "CARELINK-HMAC-SHA256-V1"
_ACCEPTED=object()


class AcceptedSensorPayload(dict):
    """In-process receipt created only AFTER the durable nonce commit."""
    def __init__(self,payload,ledger,*,proof):
        if proof is not _ACCEPTED:raise DeviceAuthError(503,"Invalid internal sensor admission")
        super().__init__(payload);self._receipt=_ACCEPTED;self._ledger=ledger;self._used=False;self._lock=threading.Lock()


def consume_receipt(payload):
    from .write_gate import CURRENT
    lease=CURRENT.get()
    if not isinstance(payload,AcceptedSensorPayload) or payload._receipt is not _ACCEPTED:
        raise HTTPException(403,"Authenticated sensor admission required")
    if not lease or not lease['valid'] or lease['path']!=payload._ledger:
        raise HTTPException(403,"Sensor admission ledger mismatch")
    with payload._lock:
        if payload._used:raise HTTPException(409,"Sensor admission already consumed")
        payload._used=True
SENSOR_PATH = "/sensor-data"
WINDOW_SECONDS = 60
MAX_BODY_BYTES = 32768
DEVICE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
HEX32 = re.compile(r"[0-9a-f]{32}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
TIMESTAMP = re.compile(r"[1-9][0-9]{9,11}\Z")


from .device_auth_errors import DeviceAuthError
from .nonce_ledger import NonceStore


def canonical_request(method: str, path: str, device: str, timestamp: str, nonce: str, body: bytes) -> bytes:
    """Seven ASCII lines, LF separators, no trailing LF. Hash EXACT body bytes."""
    return "\n".join((VERSION, method, path, device, timestamp, nonce, hashlib.sha256(body).hexdigest())).encode("ascii")


@dataclass(frozen=True)
class VerifiedRequest:
    device: str
    timestamp: int
    nonce: str


class DeviceAuthenticator:
    def __init__(self, registry: Path, nonce_db: Path):
        try:
            info = registry.stat()
            if registry.is_symlink() or not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077 or info.st_size > 1048576:
                raise ValueError("Unsafe registry")
            data = json.loads(registry.read_text())
            if data.get("version") != 1 or not isinstance(data.get("devices"), dict) or not data["devices"]:
                raise ValueError("Invalid registry")
            self.devices = {}
            api_hashes, hmac_keys = set(), set()
            for device, record in data["devices"].items():
                if not DEVICE_PATTERN.fullmatch(device) or not isinstance(record, dict):
                    raise ValueError("Invalid device")
                if not HEX64.fullmatch(record.get("api_key_sha256", "")) or not HEX64.fullmatch(record.get("hmac_key_hex", "")) or type(record.get("enabled")) is not bool:
                    raise ValueError("Invalid credential")
                if record["api_key_sha256"] in api_hashes or record["hmac_key_hex"] in hmac_keys:
                    raise ValueError("Device credentials must be independent")
                api_hashes.add(record["api_key_sha256"])
                hmac_keys.add(record["hmac_key_hex"])
                self.devices[device] = record
        except (OSError, ValueError, TypeError, AttributeError) as error:
            raise DeviceAuthError(503, "Device authentication unavailable") from error
        self.nonces = NonceStore(nonce_db)

    def verify(self, method: str, path: bytes, query: bytes, headers: Mapping[str, str], body: bytes, now: int | None = None) -> VerifiedRequest:
        now = int(time.time()) if now is None else now
        if method != "POST" or path != b"/sensor-data" or query:
            raise DeviceAuthError(400, "Noncanonical device endpoint")
        if len(body) > MAX_BODY_BYTES:
            raise DeviceAuthError(413, "Sensor request too large")
        device = headers.get("x-carelink-device-id", "")
        api_key = headers.get("x-carelink-api-key", "")
        timestamp = headers.get("x-carelink-timestamp", "")
        nonce = headers.get("x-carelink-nonce", "")
        signature = headers.get("x-carelink-signature", "")
        if not DEVICE_PATTERN.fullmatch(device) or not TIMESTAMP.fullmatch(timestamp) or not HEX32.fullmatch(nonce) or not HEX64.fullmatch(signature) or not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", api_key):
            raise DeviceAuthError(401, "Device authentication failed")
        record = self.devices.get(device)
        # Compute both comparisons even when one fails. Unknown IDs use a dummy key.
        key = bytes.fromhex(record["hmac_key_hex"]) if record else bytes(32)
        expected = hmac.new(key, canonical_request(method, SENSOR_PATH, device, timestamp, nonce, body), hashlib.sha256).hexdigest()
        key_ok = hmac.compare_digest(hashlib.sha256(api_key.encode("ascii")).hexdigest(), record["api_key_sha256"] if record else "0" * 64)
        signature_ok = hmac.compare_digest(signature, expected)
        if not key_ok or not signature_ok or not record or not record["enabled"] or abs(now - int(timestamp)) > WINDOW_SECONDS:
            raise DeviceAuthError(401, "Device authentication failed")
        return VerifiedRequest(device, int(timestamp), nonce)

    def authenticate_payload(self, method: str, path: bytes, query: bytes, headers: Mapping[str, str], body: bytes) -> dict[str, Any]:
        verified = self.verify(method, path, query, headers, body)
        if headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
            raise DeviceAuthError(415, "Sensor request must be JSON")
        payload = parse_sensor_payload(body, verified.device)
        event('hmac_timestamp_verified')
        # No nonce write occurs until signature, timestamp AND payload validation pass.
        self.nonces.reserve(verified.device, verified.nonce, verified.timestamp, int(time.time()))
        event('nonce_reserved')
        return AcceptedSensorPayload(payload,self.nonces.path,proof=_ACCEPTED)


def parse_sensor_payload(body: bytes, device: str) -> dict[str, Any]:
    def invalid_constant(_: str):
        raise ValueError("Invalid JSON number")

    def unique_object(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError("Duplicate JSON key")
            obj[key] = value
        return obj

    try:
        payload = json.loads(body.decode("utf-8"), parse_constant=invalid_constant, object_pairs_hook=unique_object)
        def finite_json(value):
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("Nonfinite number")
            if isinstance(value, dict):
                for item in value.values(): finite_json(item)
            elif isinstance(value, list):
                for item in value: finite_json(item)
        finite_json(payload)
        if not isinstance(payload, dict) or not isinstance(payload.get("device_id"), str) or not DEVICE_PATTERN.fullmatch(payload["device_id"]):
            raise ValueError("Invalid payload")
        if not hmac.compare_digest(payload["device_id"], device):
            raise DeviceAuthError(403, "Device identity mismatch")
        numeric = ("heart_rate_bpm", "object_temp_c", "ambient_temp_c", "accel_x_g", "accel_y_g", "accel_z_g", "spo2_percent")
        boolean = ("fall_detected", "heart_rate_ok", "mlx90614_ok", "mpu6050_ok", "spo2_ok")
        if not any(key in payload for key in (*numeric, *boolean)):
            raise ValueError("No sensor fields")
        for key in numeric:
            value = payload.get(key)
            if value is not None and (type(value) not in (int, float) or not math.isfinite(value)):
                raise ValueError("Invalid numeric field")
        for key in boolean:
            if key in payload and payload[key] is not None and type(payload[key]) is not bool:
                raise ValueError("Invalid boolean field")
        return payload
    except (ValueError, UnicodeError, TypeError, RecursionError, OverflowError) as error:
        raise DeviceAuthError(422, "Invalid sensor payload") from error


@lru_cache(maxsize=8)
def _cached_authenticator(registry: str, nonce_db: str, registry_identity: tuple) -> DeviceAuthenticator:
    return DeviceAuthenticator(Path(registry), Path(nonce_db))


def configured_authenticator(registry: str, nonce_db: str) -> DeviceAuthenticator:
    # A registry update/disable/rotation must take effect on the next request,
    # without waiting for a gateway restart. Atomic replacement is recommended.
    path = Path(registry)
    try:
        info = path.stat()
        if path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_size > 1048576:
            raise DeviceAuthError(503, "Device authentication unavailable")
        identity = (info.st_dev, info.st_ino, info.st_mtime_ns, info.st_ctime_ns, info.st_size)
        return _cached_authenticator(registry, nonce_db, identity)
    except OSError as error:
        raise DeviceAuthError(503, "Device authentication unavailable") from error


def preflight_device_authentication() -> None:
    """Existing-only readiness; never initializes a ledger or repairs storage."""
    root = Path(__file__).resolve().parents[1]
    registry = os.environ.get("CARELINK_DEVICE_REGISTRY", str(root / ".secrets/device-auth.json"))
    nonce_db = os.environ.get("CARELINK_DEVICE_NONCE_DB", str(root / ".secrets/device-nonces.sqlite3"))
    from .write_gate import write_lease, ControlError
    try:
        with write_lease() as selected:
            auth = configured_authenticator(registry, str(selected))
            with auth.nonces.connect(full_check=True):
                pass
    except ControlError:
        raise DeviceAuthError(503, "Device authentication unavailable") from None



async def authenticated_sensor_payload(request: Request) -> dict[str, Any]:
    try:
        if request.url.scheme != "https":
            raise DeviceAuthError(426, "HTTPS required for device requests")
        # Reject duplicate authentication headers instead of choosing one silently.
        for name in ("x-carelink-device-id", "x-carelink-api-key", "x-carelink-timestamp", "x-carelink-nonce", "x-carelink-signature"):
            if len(request.headers.getlist(name)) != 1:
                raise DeviceAuthError(401, "Device authentication failed")
        data = bytearray()
        async for chunk in request.stream():
            if len(data) + len(chunk) > MAX_BODY_BYTES:
                raise DeviceAuthError(413, "Sensor request too large")
            data.extend(chunk)
        root = Path(__file__).resolve().parents[1]
        registry = os.environ.get("CARELINK_DEVICE_REGISTRY", str(root / ".secrets/device-auth.json"))
        nonce_db = os.environ.get("CARELINK_DEVICE_NONCE_DB", str(root / ".secrets/device-nonces.sqlite3"))

        nonce_db = request.scope.get("carelink_managed_ledger")
        if not nonce_db:
            raise DeviceAuthError(503, "Unified device admission required")

        def validate():
            auth = configured_authenticator(registry, nonce_db)
            return auth.authenticate_payload(request.method, request.scope.get("raw_path", b""), request.scope.get("query_string", b""), request.headers, bytes(data))

        return await run_in_threadpool(validate)
    except DeviceAuthError as error:
        event('authentication_rejected', error.status)
        raise HTTPException(status_code=error.status, detail=error.detail) from None
    except (OSError, sqlite3.Error):
        event('storage_unavailable', 503)
        raise HTTPException(status_code=503, detail="Device authentication unavailable") from None
