from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import time
from typing import Any, Optional

from fastapi import Cookie, Depends, FastAPI, HTTPException, Query, Response, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, SecretStr, Field, ConfigDict

from .classification_service import classify_values, model_info
from .write_gate import UnifiedWriteGate, guarded_write
from .device_auth import authenticated_sensor_payload, consume_receipt
from .web_auth import store as auth_store, TTL, verify_password, bootstrap_accounts
from .web_security import WebSecurity
from .device_diagnostics import DeviceIngressDiagnostics, event as device_event


ROOT = Path(__file__).resolve().parents[1]
DATABASE_PATH = Path(
    os.environ.get("CARELINK_DATABASE_PATH", Path(__file__).with_name("carelink.db"))
)
STALE_AFTER_SECONDS = 60
PATIENT_ID = "ttj"

USERS = {
    "ttj": {
        "password_hash": os.environ.get(
            "CARELINK_PATIENT_PASSWORD_HASH",
            "",
        ),
        "role": "patient",
        "mode": "basic",
        "patient_ids": [PATIENT_ID],
    },
    "wyn": {
        "password_hash": os.environ.get(
            "CARELINK_NURSE_PASSWORD_HASH",
            "",
        ),
        "role": "clinician",
        "mode": "pro",
        "patient_ids": [PATIENT_ID],
    },
}
PATIENT = {
    "id": PATIENT_ID,
    "name": "Patient TTJ",
    "age": 68,
    "sex": "Patient",
    "history": "CareLink monitored patient profile.",
    "bed": "Home-01",
    "color": "mint",
    "admittedAt": "2026-10-15",
    "allergies": "Not recorded",
}

class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: SecretStr = Field(min_length=1, max_length=1024)


class ClassificationRequest(BaseModel):
    heart_rate: float
    temperature: float
    fall: bool = False


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _verify_password(password: str, encoded: str) -> bool:
    return verify_password(password, encoded)[0]


def _read_session_token(token: Optional[str]) -> Optional[str]:
    return auth_store().username(token)


class LeasedCursor(sqlite3.Cursor):
    def execute(self,*args,**kwargs):
        self.connection.require_execution(args[0]);return super().execute(*args,**kwargs)
    def executemany(self,*args,**kwargs):
        self.connection.require_execution(args[0]);return super().executemany(*args,**kwargs)
    def executescript(self,*args,**kwargs):
        self.connection.require_execution(args[0],script=True);return super().executescript(*args,**kwargs)


class LeasedConnection(sqlite3.Connection):
    def require_execution(self,sql,script=False):
        self.require_lease()
        if getattr(self,'_read_only',False) and (script or not sql.lstrip().upper().startswith('SELECT ')):
            raise sqlite3.OperationalError('Read-only database lease')
    def require_lease(self):
        from .write_gate import CURRENT
        lease=getattr(self,'_lease',None)
        if not lease or not lease['valid'] or CURRENT.get() is not lease:
            raise sqlite3.OperationalError('Active database write lease required')
    def execute(self,*args,**kwargs):
        return self.cursor().execute(*args,**kwargs)
    def executemany(self,*args,**kwargs):
        return self.cursor().executemany(*args,**kwargs)
    def executescript(self,*args,**kwargs):
        return self.cursor().executescript(*args,**kwargs)
    def cursor(self,*args,**kwargs):
        self.require_lease()
        if args or kwargs:raise sqlite3.OperationalError('Custom cursor factories are unavailable')
        return super().cursor(factory=LeasedCursor)
    def commit(self):self.require_lease();return super().commit()
    def rollback(self):self.require_lease();return super().rollback()
    def __enter__(self):self.require_lease();return self
    def __exit__(self,kind,value,tb):
        try:
            if kind is None:self.commit()
            else:super().rollback()
        finally:self.close()
    def close(self):
        guard=getattr(self,'_guard',None)
        self._guard=None
        try:super().close() # Always rolls back uncommitted work, even after lease loss.
        finally:
            if guard is not None:guard.__exit__(None,None,None)


def connect() -> sqlite3.Connection:
    from .write_gate import CURRENT,write_lease,ControlError
    existing=CURRENT.get()
    read_only=not (existing and existing['valid'])
    guard=write_lease()
    try:guard.__enter__()
    except ControlError:raise HTTPException(503,'Database reception frozen or unavailable') from None
    connection=None
    try:
        from .storage_paths import validate_storage_paths
        validate_storage_paths(readings=DATABASE_PATH)
        connection=sqlite3.connect(DATABASE_PATH.absolute().as_uri()+"?mode=rw",uri=True,timeout=15,cached_statements=0,factory=LeasedConnection)
        connection._lease=CURRENT.get();connection._guard=guard
        connection.row_factory=sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON');connection.execute('PRAGMA busy_timeout=15000')
        if read_only:
            connection.execute('PRAGMA query_only=ON')
            connection._read_only=True
        return connection
    except BaseException:
        if connection is not None:connection.close()
        else:guard.__exit__(None,None,None)
        raise


@guarded_write
def initialize_database() -> None:
    from .storage_paths import validate_storage_paths
    validate_storage_paths(readings=DATABASE_PATH)
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not DATABASE_PATH.exists():
        fd=os.open(DATABASE_PATH,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        os.close(fd)
    with connect() as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id TEXT NOT NULL,
                device_id TEXT NOT NULL,
                heart_rate REAL,
                temperature REAL,
                fall_detected INTEGER,
                label TEXT CHECK(label IN ('normal', 'warning', 'critical') OR label IS NULL),
                confidence REAL,
                model_name TEXT,
                model_version TEXT,
                abnormal_params TEXT NOT NULL DEFAULT '[]',
                validation_errors TEXT NOT NULL DEFAULT '[]',
                raw_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_readings_patient_time ON readings(patient_id, created_at DESC)")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id TEXT NOT NULL,
                alert_key TEXT NOT NULL,
                type TEXT NOT NULL,
                severity TEXT NOT NULL,
                summary TEXT NOT NULL,
                details TEXT NOT NULL DEFAULT '{{}}',
                status TEXT NOT NULL DEFAULT 'new',
                condition_active INTEGER NOT NULL DEFAULT 1,
                occurrence_count INTEGER NOT NULL DEFAULT 1,
                occurred_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                acknowledged_at TEXT,
                acknowledged_by TEXT,
                resolved_at TEXT,
                reading_id INTEGER,
                FOREIGN KEY(reading_id) REFERENCES readings(id)
            )
            """
        )
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_alerts_one_unresolved
            ON alerts(patient_id, alert_key)
            WHERE status IN ('new', 'acknowledged')
            """
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_alerts_patient_time ON alerts(patient_id, updated_at DESC)")


@asynccontextmanager
async def lifespan(application: FastAPI):
    if getattr(application.state, "web_auth_enabled", True):
        if auth_store().path.resolve() == DATABASE_PATH.resolve():
            raise RuntimeError("Auth and readings databases must be separate")
        auth_store().initialize({} if auth_store().marker.exists() else bootstrap_accounts(USERS))
    initialize_database()
    model_info()
    yield


app = FastAPI(
    title="CareLink Health Monitoring API",
    description="Educational API for heart rate, temperature and fall monitoring.",
    version="3.0.0",
    lifespan=lifespan,
)
app.add_middleware(WebSecurity)
app.add_middleware(UnifiedWriteGate)
app.add_middleware(DeviceIngressDiagnostics)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    # FastAPI's default includes rejected input values, including login secrets.
    return JSONResponse(status_code=422, content={"detail": "Invalid request data"})


def _session_payload(username: str) -> dict[str, Any]:
    account = auth_store().account(username)
    return {
        "userId": username,
        "role": account["role"],
        "mode": account["mode"],
        "patientIds": account["patient_ids"],
    }


def current_username(carelink_session: Optional[str] = Cookie(default=None)) -> str:
    username = _read_session_token(carelink_session)
    if not username:
        raise HTTPException(status_code=401, detail="Authentication required")
    return username


def _ensure_scope(username: str, patient_id: str) -> None:
    if patient_id not in auth_store().account(username)["patient_ids"]:
        raise HTTPException(status_code=403, detail="Patient is outside this account's scope")


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _first(payload: dict[str, Any], *candidates: tuple[str, ...]) -> Any:
    for path in candidates:
        value: Any = payload
        for key in path:
            if not isinstance(value, dict) or key not in value:
                value = None
                break
            value = value[key]
        if value is not None:
            return value
    return None


def _extract(payload: dict[str, Any]) -> tuple[Optional[float], Optional[float], Optional[bool]]:
    heart_ok = _first(payload, ("heart_rate_ok",), ("heart_rate", "ok"))
    heart = _number(_first(payload, ("heart_rate_bpm",), ("heart_rate", "bpm")))
    # A held LCD/display value is historical, not a new pulse measurement.
    if heart is None and heart_ok is True and payload.get("heart_rate_held") is not True:
        heart = _number(_first(payload, ("heart_rate_display_bpm",), ("heart_rate", "display_bpm")))
    if heart_ok is False or payload.get("heart_rate_held") is True:
        heart = None
    temperature = _number(_first(payload, ("object_temp_c",), ("mlx90614", "object_temp_c"), ("temperature",)))
    if _first(payload, ("mlx90614_ok",), ("mlx90614", "ok")) is False:
        temperature = None
    fall_raw = _first(payload, ("fall_detected",), ("mpu6050", "fall_detected"), ("alarm",))
    fall = bool(fall_raw) if isinstance(fall_raw, (bool, int)) else None
    if _first(payload, ("mpu6050_ok",), ("mpu6050", "ok")) is False:
        fall = None
    return heart, temperature, fall


def _oxygen(payload: dict[str, Any]) -> Optional[float]:
    value = _number(_first(payload, ("spo2_percent",), ("spo2", "percent"), ("max30102", "spo2"), ("spo2",)))
    if _first(payload, ("spo2_ok",), ("spo2", "ok"), ("max30102", "ok")) is False:
        return None
    return value


def _validate_inputs(heart: Optional[float], temperature: Optional[float], fall: Optional[bool]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    if heart is None:
        errors.append({"parameter": "heart_rate_bpm", "kind": "missing_data", "reason": "Heart rate is missing."})
    elif not 30 <= heart <= 250:
        errors.append({"parameter": "heart_rate_bpm", "kind": "invalid_reading", "value": heart, "reason": "Heart rate must be between 30 and 250 BPM."})
    if temperature is None:
        errors.append({"parameter": "temperature_c", "kind": "missing_data", "reason": "Temperature is missing."})
    elif not 30 <= temperature <= 45:
        errors.append({"parameter": "temperature_c", "kind": "invalid_reading", "value": temperature, "reason": "Temperature must be between 30 and 45 °C."})
    if fall is None:
        errors.append({"parameter": "fall_detected", "kind": "missing_data", "reason": "Fall state is missing."})
    return errors


def _upsert_alert(
    connection: sqlite3.Connection,
    *,
    alert_key: str,
    alert_type: str,
    severity: str,
    summary: str,
    details: dict[str, Any],
    timestamp: str,
    reading_id: Optional[int],
) -> None:
    connection.execute(
        """
        INSERT INTO alerts (
            patient_id, alert_key, type, severity, summary, details,
            status, condition_active, occurrence_count, occurred_at,
            updated_at, reading_id
        ) VALUES (?, ?, ?, ?, ?, ?, 'new', 1, 1, ?, ?, ?)
        ON CONFLICT(patient_id, alert_key) WHERE status IN ('new', 'acknowledged')
        DO UPDATE SET
            type=excluded.type,
            severity=excluded.severity,
            summary=excluded.summary,
            details=excluded.details,
            condition_active=1,
            occurrence_count=alerts.occurrence_count+1,
            updated_at=excluded.updated_at,
            reading_id=excluded.reading_id
        """,
        (PATIENT_ID, alert_key, alert_type, severity, summary, json.dumps(details, ensure_ascii=False), timestamp, timestamp, reading_id),
    )


def _resolve_inactive_alerts(connection: sqlite3.Connection, active_keys: set[str], timestamp: str) -> None:
    rows = connection.execute(
        "SELECT alert_key FROM alerts WHERE patient_id=? AND status IN ('new', 'acknowledged')",
        (PATIENT_ID,),
    ).fetchall()
    for row in rows:
        if row["alert_key"] not in active_keys:
            connection.execute(
                """
                UPDATE alerts SET status='resolved', condition_active=0,
                    resolved_at=?, updated_at=?
                WHERE patient_id=? AND alert_key=? AND status IN ('new', 'acknowledged')
                """,
                (timestamp, timestamp, PATIENT_ID, row["alert_key"]),
            )


def _store_alerts(
    connection: sqlite3.Connection,
    reading_id: int,
    prediction: Optional[dict[str, Any]],
    validation_errors: list[dict[str, Any]],
    timestamp: str,
    oxygen: Optional[float] = None,
) -> None:
    active_keys: set[str] = set()
    if oxygen is not None and 0 < oxygen <= 100 and oxygen < 95:
        active_keys.add("abnormal:spo2_percent")
        _upsert_alert(connection, alert_key="abnormal:spo2_percent", alert_type="abnormal_parameter",
                      severity="red" if oxygen < 90 else "yellow", summary="Device reported low SpO2; verify the sensor and patient.",
                      details={"parameter":"spo2_percent","value":oxygen,"source":"optional_sensor"}, timestamp=timestamp, reading_id=reading_id)
    for error in validation_errors:
        key = f"{error['kind']}:{error['parameter']}"
        active_keys.add(key)
        _upsert_alert(
            connection,
            alert_key=key,
            alert_type=error["kind"],
            severity="yellow",
            summary=error["reason"],
            details=error,
            timestamp=timestamp,
            reading_id=reading_id,
        )
    if prediction and prediction["label"] in {"warning", "critical"}:
        active_keys.add("classification")
        _upsert_alert(
            connection,
            alert_key="classification",
            alert_type="classification",
            severity="red" if prediction["label"] == "critical" else "yellow",
            summary=f"Model classification: {prediction['label']} ({prediction['confidence'] * 100:.1f}% confidence).",
            details={"label": prediction["label"], "confidence": prediction["confidence"]},
            timestamp=timestamp,
            reading_id=reading_id,
        )
        for item in prediction["abnormal_params"]:
            key = f"abnormal:{item['parameter']}"
            active_keys.add(key)
            _upsert_alert(
                connection,
                alert_key=key,
                alert_type="abnormal_parameter",
                severity="red" if item["severity"] == "critical" else "yellow",
                summary=item["reason"],
                details=item,
                timestamp=timestamp,
                reading_id=reading_id,
            )
    _resolve_inactive_alerts(connection, active_keys, timestamp)


@guarded_write
def _ensure_connectivity_alert() -> None:
    now = datetime.now(timezone.utc)
    with connect() as connection:
        row = connection.execute("SELECT created_at FROM readings WHERE patient_id=? ORDER BY id DESC LIMIT 1", (PATIENT_ID,)).fetchone()
        if row is None:
            _upsert_alert(
                connection,
                alert_key="missing_data:no_readings",
                alert_type="missing_data",
                severity="yellow",
                summary="No sensor readings have been received.",
                details={"parameter": "sensor_snapshot", "kind": "missing_data"},
                timestamp=now.isoformat(),
                reading_id=None,
            )
            return
        try:
            age = now - datetime.fromisoformat(row["created_at"])
        except ValueError:
            age = timedelta.max
        if age.total_seconds() > STALE_AFTER_SECONDS:
            _upsert_alert(
                connection,
                alert_key="network_failure",
                alert_type="network_failure",
                severity="yellow",
                summary=f"No device update for more than {STALE_AFTER_SECONDS} seconds.",
                details={"last_received_at": row["created_at"], "age_seconds": int(age.total_seconds())},
                timestamp=now.isoformat(),
                reading_id=None,
            )


def _latest_row(patient_id: str) -> Optional[Any]:
    with connect() as connection:
        return connection.execute("SELECT * FROM readings WHERE patient_id=? ORDER BY id DESC LIMIT 1", (patient_id,)).fetchone()


def _raw_vector(raw: dict[str, Any]) -> Optional[dict[str, float]]:
    x = _number(_first(raw, ("accel_x_g",), ("mpu6050", "acceleration_g", "x")))
    y = _number(_first(raw, ("accel_y_g",), ("mpu6050", "acceleration_g", "y")))
    z = _number(_first(raw, ("accel_z_g",), ("mpu6050", "acceleration_g", "z")))
    if x is None or y is None or z is None:
        return None
    return {"x": x * 9.80665, "y": y * 9.80665, "z": z * 9.80665}


def _prediction_from_row(row: Any) -> dict[str, Any]:
    validation = _validate_inputs(*_extract(json.loads(row["raw_json"])))
    if row["label"] is None or validation:
        return {
            "state": "unavailable",
            "id": f"prediction-{row['id']}",
            "patientId": row["patient_id"],
            "predictedAt": row["created_at"],
            "inputsMeasuredAt": row["created_at"],
            "model": row["model_name"],
            "modelVersion": row["model_version"],
            "result": {"label": None, "abnormal_params": validation or json.loads(row["validation_errors"])},
            "confidence": None,
            "confidenceMeaning": "No model output because required sensor data was missing or invalid.",
            "source": "backend",
        }
    return {
        "state": "available",
        "id": f"prediction-{row['id']}",
        "patientId": row["patient_id"],
        "predictedAt": row["created_at"],
        "inputsMeasuredAt": row["created_at"],
        "model": row["model_name"],
        "modelVersion": row["model_version"],
        "result": {"label": row["label"], "abnormal_params": json.loads(row["abnormal_params"])},
        "confidence": row["confidence"],
        "confidenceMeaning": "Probability assigned to the selected class by the trained model.",
        "source": "backend",
    }


def _reading_from_row(row: Any) -> dict[str, Any]:
    raw = json.loads(row["raw_json"])
    heart, temperature, fall = _extract(raw)
    validation = _validate_inputs(heart, temperature, fall)
    abnormal = json.loads(row["abnormal_params"])
    timestamp = datetime.fromisoformat(row["created_at"])
    connected = (datetime.now(timezone.utc) - timestamp).total_seconds() <= STALE_AFTER_SECONDS
    heart_valid = heart is not None and 30 <= heart <= 250
    # The classifier's 30–45 °C domain is not the surface sensor's validity flag.
    temperature_valid = temperature is not None
    fall_available = fall is not None
    oxygen = _oxygen(raw)
    oxygen_valid = oxygen is not None and 0 < oxygen <= 100
    level = "unknown" if validation else {"normal": "green", "warning": "yellow", "critical": "red"}.get(row["label"], "unknown")
    reasons = [item["reason"] for item in validation] if validation else [item["reason"] for item in abnormal]
    if not reasons:
        reasons = ["The trained model classified the complete sensor snapshot as normal."]
    if oxygen_valid and oxygen < 95:
        level = "red" if oxygen < 90 or level == "red" else "yellow"
        reasons.append("Optional sensor reports low SpO2; verify the reading and patient.")
    elif oxygen is not None and not oxygen_valid:
        if level == "green": level = "unknown"
        reasons.append("Optional SpO2 sample is outside 0–100%; do not treat it as a valid reading.")
    assessment = {
        "level": level,
        "reasons": reasons,
        "assessedAt": row["created_at"],
        "ruleSetId": f"{row['model_name']}:{row['model_version']}" if row["model_name"] else None,
        "origin": "backend",
    }
    return {
        "patientId": row["patient_id"],
        "deviceId": row["device_id"],
        "measuredAt": row["created_at"],
        "receivedAt": row["created_at"],
        "connected": connected,
        "metrics": {
            "hr": {"value": heart, "quality": "good" if heart_valid else "poor" if heart is not None else "unavailable", "available": heart is not None},
            "temp": {"value": temperature, "quality": "good" if temperature_valid else "unavailable", "available": temperature_valid},
            **({"spo2": {"value": oxygen, "quality": "good" if oxygen_valid else "poor" if oxygen is not None else "unavailable", "available": oxygen is not None}} if any(key in raw for key in ("spo2_percent","spo2","max30102")) else {}),
        },
        "fall": {"active": bool(fall), "quality": "good" if fall_available else "unavailable", "eventAt": row["created_at"] if fall else None},
        "raw": {
            "accel_m_s2": _raw_vector(raw),
            "gyro_deg_s": None,
            "ir": _number(_first(raw, ("heart_signal_raw",), ("heart_rate", "signal_raw"))),
            "red": None,
            "object_temperature_c": row["temperature"],
            "ambient_temperature_c": _number(_first(raw, ("ambient_temp_c",), ("mlx90614", "ambient_temp_c"))),
        },
        "ai": _prediction_from_row(row),
        "source": "mock" if os.environ.get("CARELINK_DATA_ORIGIN") == "simulation" or raw.get("data_source") in ("simulation", "simulated", "coursework-simulator") else "device",
        "assessment": assessment,
    }


def _patient_payload() -> dict[str, Any]:
    row = _latest_row(PATIENT_ID)
    return {**PATIENT, "reading": _reading_from_row(row) if row else None}


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "service": "carelink-api", "model": model_info().get("selected_model")}


def _set_session_cookie(response: Response, token: str, max_age: int = TTL):
    response.set_cookie("carelink_session", token, httponly=True, samesite="lax",
                        secure=True, max_age=max_age, path="/")


@app.post("/api/login")
def login(request: LoginRequest, response: Response, connection: Request,
          carelink_session: Optional[str] = Cookie(default=None)) -> dict[str, Any]:
    password = request.password.get_secret_value()
    if len(password.encode("utf-8")) > 1024:
        raise HTTPException(422, "Invalid request data")
    username = request.username.strip().lower()
    token = auth_store().login(username, password,
                              connection.client.host if connection.client else "unknown", carelink_session)
    _set_session_cookie(response, token)
    return _session_payload(username)


@app.post("/api/logout")
def logout(response: Response, carelink_session: Optional[str] = Cookie(default=None)) -> dict[str, str]:
    auth_store().revoke(carelink_session)
    response.delete_cookie("carelink_session", path="/", secure=True, httponly=True, samesite="lax")
    return {"status": "signed_out"}


@app.post("/api/session/rotate")
def rotate_session(response: Response, carelink_session: Optional[str] = Cookie(default=None)) -> dict[str, str]:
    token, remaining = auth_store().rotate(carelink_session)
    _set_session_cookie(response, token, remaining)
    return {"status": "rotated"}


@app.get("/api/session")
def session(username: str = Depends(current_username)) -> dict[str, Any]:
    return _session_payload(username)


@app.get("/api/gateway")
def gateway_info(_: str = Depends(current_username)) -> dict[str, Any]:
    # Configuration provenance is not evidence that physical hardware is online.
    mode = os.environ.get("CARELINK_DATA_ORIGIN", "unspecified")
    return {"mode":mode, "sensorPath":"/sensor-data", "serverPatientId":PATIENT_ID,
            "hasAutomaticSimulator":mode == "simulation", "staleAfterSeconds":STALE_AFTER_SECONDS}


@app.get("/api/patients")
def patients(username: str = Depends(current_username)) -> list[dict[str, Any]]:
    _ensure_scope(username, PATIENT_ID)
    return [_patient_payload()]


@app.get("/api/patients/{patient_id}")
def patient(patient_id: str, username: str = Depends(current_username)) -> dict[str, Any]:
    _ensure_scope(username, patient_id)
    return _patient_payload()


@app.get("/api/patients/{patient_id}/readings")
def readings(
    patient_id: str,
    minutes: int = Query(default=1440, ge=1, le=43200),
    username: str = Depends(current_username),
) -> list[dict[str, Any]]:
    _ensure_scope(username, patient_id)
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    with connect() as connection:
        rows = connection.execute(
            "SELECT * FROM readings WHERE patient_id=? AND created_at>=? ORDER BY created_at DESC LIMIT 2000",
            (patient_id, cutoff),
        ).fetchall()
    return [_reading_from_row(row) for row in rows]


@app.get("/api/patients/{patient_id}/predictions")
def predictions(patient_id: str, username: str = Depends(current_username)) -> list[dict[str, Any]]:
    _ensure_scope(username, patient_id)
    with connect() as connection:
        rows = connection.execute(
            "SELECT * FROM readings WHERE patient_id=? ORDER BY created_at DESC LIMIT 100",
            (patient_id,),
        ).fetchall()
    return [_prediction_from_row(row) for row in rows]


@app.get("/api/alerts")
def alerts(username: str = Depends(current_username)) -> list[dict[str, Any]]:
    _ensure_connectivity_alert()
    patient_ids = auth_store().account(username)["patient_ids"]
    placeholders = ",".join("?" for _ in patient_ids)
    with connect() as connection:
        rows = connection.execute(
            f"SELECT * FROM alerts WHERE patient_id IN ({placeholders}) ORDER BY updated_at DESC LIMIT 500",
            patient_ids,
        ).fetchall()
    return [
        {
            "id": f"alert-{row['id']}",
            "patientId": row["patient_id"],
            "type": row["type"],
            "severity": row["severity"],
            "occurredAt": row["occurred_at"],
            "updatedAt": row["updated_at"],
            "acknowledgedAt": row["acknowledged_at"],
            "acknowledgedBy": row["acknowledged_by"],
            "status": row["status"],
            "conditionActive": bool(row["condition_active"]),
            "resolvedAt": row["resolved_at"],
            "summary": row["summary"],
            "source": "backend",
        }
        for row in rows
    ]


@app.post("/api/alerts/{alert_id}/acknowledgement")
@guarded_write
def acknowledge(alert_id: str, username: str = Depends(current_username)) -> dict[str, Any]:
    if auth_store().account(username)["role"] != "clinician":
        raise HTTPException(status_code=403, detail="Nurse role required")
    try:
        numeric_id = int(alert_id.removeprefix("alert-"))
    except ValueError as error:
        raise HTTPException(status_code=404, detail="Alert not found") from error
    timestamp = utc_now()
    with connect() as connection:
        row = connection.execute("SELECT * FROM alerts WHERE id=?", (numeric_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Alert not found")
        _ensure_scope(username, row["patient_id"])
        if row["status"] == "resolved":
            raise HTTPException(status_code=409, detail="Resolved alert cannot be acknowledged")
        connection.execute(
            "UPDATE alerts SET status='acknowledged', acknowledged_at=COALESCE(acknowledged_at,?), acknowledged_by=COALESCE(acknowledged_by,?), updated_at=? WHERE id=?",
            (timestamp, username, timestamp, numeric_id),
        )
        row = connection.execute("SELECT * FROM alerts WHERE id=?", (numeric_id,)).fetchone()
    return {
        "id": f"alert-{row['id']}", "patientId": row["patient_id"], "type": row["type"],
        "severity": row["severity"], "occurredAt": row["occurred_at"], "updatedAt": row["updated_at"],
        "acknowledgedAt": row["acknowledged_at"], "acknowledgedBy": row["acknowledged_by"],
        "status": row["status"], "conditionActive": bool(row["condition_active"]),
        "resolvedAt": row["resolved_at"], "summary": row["summary"], "source": "backend",
    }


@app.post("/api/classify")
def classify(request: ClassificationRequest, _: str = Depends(current_username)) -> dict[str, Any]:
    try:
        return classify_values(request.heart_rate, request.temperature, request.fall)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/sensor-data")
@guarded_write
def receive_sensor_data(payload: dict[str, Any] = Depends(authenticated_sensor_payload)) -> dict[str, Any]:
    consume_receipt(payload)
    device_id = payload.get("device_id")
    if not isinstance(device_id, str) or not device_id.strip():
        raise HTTPException(status_code=422, detail="device_id is required")
    heart, temperature, fall = _extract(payload)
    validation_errors = _validate_inputs(heart, temperature, fall)
    prediction: Optional[dict[str, Any]] = None
    if not validation_errors:
        prediction = classify_values(float(heart), float(temperature), bool(fall))
    timestamp = utc_now()
    with connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO readings (
                patient_id, device_id, heart_rate, temperature, fall_detected,
                label, confidence, model_name, model_version, abnormal_params,
                validation_errors, raw_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                PATIENT_ID, device_id.strip(), heart, temperature,
                int(fall) if fall is not None else None,
                prediction["label"] if prediction else None,
                prediction["confidence"] if prediction else None,
                prediction["model"] if prediction else model_info().get("selected_model"),
                prediction["model_version"] if prediction else str(model_info().get("trained_at") or "1.0"),
                json.dumps(prediction["abnormal_params"] if prediction else [], ensure_ascii=False),
                json.dumps(validation_errors, ensure_ascii=False),
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                timestamp,
            ),
        )
        reading_id = int(cursor.lastrowid)
        _store_alerts(connection, reading_id, prediction, validation_errors, timestamp, _oxygen(payload))
    device_event('readings_committed')
    return {
        "status": "received",
        "id": reading_id,
        "received_at": timestamp,
        "label": prediction["label"] if prediction else None,
        "classification": prediction["label"] if prediction else None,
        "confidence": prediction["confidence"] if prediction else None,
        "abnormal_params": prediction["abnormal_params"] if prediction else validation_errors,
        "validation_errors": validation_errors,
        "actions": {
            "buzzer": bool(prediction and prediction["label"] in {"warning", "critical"}),
        },
    }


BUILD_DIR = ROOT / "build"
if BUILD_DIR.exists():
    app.mount("/", StaticFiles(directory=BUILD_DIR, html=True), name="web")
