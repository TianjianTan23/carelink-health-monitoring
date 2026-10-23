from datetime import datetime
from typing import Any
import json

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="CareLink Local Sensor Bridge")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

latest_payload: dict[str, Any] | None = None
latest_received_at: str | None = None


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "carelink-sensor-bridge",
    }


@app.post("/sensor-data")
async def receive_sensor_data(
    payload: dict[str, Any],
    request: Request,
) -> dict[str, Any]:
    global latest_payload, latest_received_at

    latest_payload = payload
    latest_received_at = datetime.now().astimezone().isoformat()

    client_ip = request.client.host if request.client else "unknown"

    print(
        f"\n[{latest_received_at}] "
        f"Sensor data received from {client_ip}"
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))

    return {
        "ok": True,
        "received": True,
        "device_id": payload.get("device_id"),
    }


@app.get("/sensor-data/latest")
def get_latest_sensor_data() -> dict[str, Any]:
    if latest_payload is None:
        raise HTTPException(
            status_code=503,
            detail="No sensor data received yet",
        )

    return {
        "ok": True,
        "received_at": latest_received_at,
        "data": latest_payload,
    }
