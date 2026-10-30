"""Optional parallel TLS device ingress for an approved no-restart migration.

Only /health and authenticated /sensor-data exist. No Web, login, session or docs
are exposed. It uses the SAME reading DB and durable nonce ledger as backend.app.
This module never starts a listener by itself and is not enabled automatically.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from starlette.concurrency import run_in_threadpool
from .app import lifespan, receive_sensor_data
from .write_gate import UnifiedWriteGate
from .device_auth import preflight_device_authentication, DeviceAuthError


@asynccontextmanager
async def device_lifespan(application):
    # Fail BEFORE initializing the readings DB/model or becoming ready.
    await run_in_threadpool(preflight_device_authentication)
    async with lifespan(application):
        yield


app = FastAPI(title="CareLink Device Ingress", docs_url=None, redoc_url=None, openapi_url=None, lifespan=device_lifespan)
app.state.web_auth_enabled = False
app.add_middleware(UnifiedWriteGate)
app.add_api_route("/sensor-data", receive_sensor_data, methods=["POST"])


@app.get("/health")
async def health():
    try:
        await run_in_threadpool(preflight_device_authentication)
    except DeviceAuthError:
        raise HTTPException(status_code=503, detail="Device authentication unavailable") from None
    return {"status":"ok", "service":"carelink-device-ingress"}
