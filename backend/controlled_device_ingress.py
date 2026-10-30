"""Opt-in managed device receiver. Existing gateways are not changed/imported.

For a future reviewed launcher: --factory backend.controlled_device_ingress:create_from_environment
All device writes sharing a ledger must use this protocol. Missing config fails.
"""
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse
from .ledger_control import Controller, ControlError
from .device_auth import DeviceAuthError, configured_authenticator, authenticated_sensor_payload, MAX_BODY_BYTES


from .write_gate import UnifiedWriteGate

AdmissionMiddleware = UnifiedWriteGate


def create_app(control_root,registry, *, receiver=None, lifespan=None):
    controller=Controller(control_root)
    controller.state()  # Missing/invalid controls never auto-enroll.
    if receiver is None:
        from .app import receive_sensor_data, lifespan as original_lifespan
        receiver,lifespan=receive_sensor_data,original_lifespan
    app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)
    app.state.web_auth_enabled=False

    async def authenticate(request:Request):
        try:
            if request.url.scheme!="https":raise DeviceAuthError(426,"HTTPS required for device requests")
            for name in ("x-carelink-device-id","x-carelink-api-key","x-carelink-timestamp","x-carelink-nonce","x-carelink-signature"):
                if len(request.headers.getlist(name))!=1:raise DeviceAuthError(401,"Device authentication failed")
            data=bytearray()
            async for chunk in request.stream():
                if len(data)+len(chunk)>MAX_BODY_BYTES:raise DeviceAuthError(413,"Sensor request too large")
                data.extend(chunk)
            def verify():
                auth=configured_authenticator(str(registry),request.scope["carelink_managed_ledger"])
                return auth.authenticate_payload(request.method,request.scope.get("raw_path",b""),request.scope.get("query_string",b""),request.headers,bytes(data))
            return await run_in_threadpool(verify)
        except DeviceAuthError as error:raise HTTPException(error.status,error.detail) from None
        except Exception:raise HTTPException(503,"Device authentication unavailable") from None

    app.dependency_overrides[authenticated_sensor_payload]=authenticate
    app.add_api_route("/sensor-data",receiver,methods=["POST"])
    app.add_middleware(AdmissionMiddleware,controller=controller)

    @app.get("/health")
    async def health():
        def check():
            with controller.admission():pass
        try:await run_in_threadpool(check)
        except Exception:raise HTTPException(503,"Device reception frozen or unavailable") from None
        return {"status":"ok","service":"carelink-controlled-device-ingress"}
    return app


def create_from_environment():
    required=("CARELINK_LEDGER_CONTROL_ROOT","CARELINK_DEVICE_REGISTRY","CARELINK_DATABASE_PATH")
    if any(not os.environ.get(name) or not Path(os.environ[name]).is_absolute() for name in required):
        raise RuntimeError("Explicit managed receiver paths required")
    return create_app(os.environ[required[0]],os.environ[required[1]])
