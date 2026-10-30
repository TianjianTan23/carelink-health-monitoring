"""Synthetic credentials for tests ONLY; no local/real device keys are loaded."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import time

from .nonce_ledger import initialize_new_ledger, AUTHORIZATION


def fixture_credentials(device):
    return "fixture_api_key_" + hashlib.sha256(device.encode()).hexdigest(), hashlib.sha256(("fixture-hmac-" + device).encode()).digest()


def write_registry(path, devices=("esp32-test", "quality-test")):
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    records = {}
    for device in devices:
        api, key = fixture_credentials(device)
        records[device] = {"enabled":True, "api_key_sha256":hashlib.sha256(api.encode()).hexdigest(), "hmac_key_hex":key.hex()}
    path.write_text(json.dumps({"version":1,"devices":records}))
    path.chmod(0o600)


def signed_headers(body, device="esp32-test", *, timestamp=None, nonce=None, method="POST", path="/sensor-data"):
    api, key = fixture_credentials(device)
    timestamp = str(int(time.time()) if timestamp is None else timestamp)
    nonce = secrets.token_hex(16) if nonce is None else nonce
    # Independent protocol encoder, intentionally not importing canonical_request.
    canonical = ("CARELINK-HMAC-SHA256-V1\n" + method + "\n" + path + "\n" + device + "\n" + timestamp + "\n" + nonce + "\n" + hashlib.sha256(body).hexdigest()).encode("ascii")
    return {"Content-Type":"application/json", "X-CareLink-Device-Id":device,
            "X-CareLink-Api-Key":api, "X-CareLink-Timestamp":timestamp,
            "X-CareLink-Nonce":nonce, "X-CareLink-Signature":hmac.new(key,canonical,hashlib.sha256).hexdigest()}


def fixture_device_control(directory, nonce_db=None):
    """Explicit synthetic enrollment, not a production bypass flag."""
    from .ledger_control import Controller, fingerprint, history, private_new, sql
    from .nonce_ledger import NonceStore
    directory=Path(directory);private=directory/'auth';private.mkdir(mode=0o700,parents=True,exist_ok=True)
    nonce_db=Path(nonce_db) if nonce_db else private/'nonces.sqlite3'
    if not nonce_db.exists():initialize_new_ledger(nonce_db,authorization=AUTHORIZATION)
    control=private/'control'
    if not control.exists():
        with sql(nonce_db) as db:rows=history(db)
        if not rows:NonceStore(nonce_db).reserve('fixture-bootstrap','f'*32,int(time.time()),int(time.time()))
        with sql(nonce_db) as db:checkpoint=fingerprint(history(db))
        info=nonce_db.stat();receipt=private/'inventory.json'
        private_new(receipt,(json.dumps({'source':str(nonce_db),'device':info.st_dev,'inode':info.st_ino,
          'checkpoint':checkpoint,'all_writers_controlled':True,'legacy_writers_stopped':True,
          'expires_at':int(time.time())+3600,'review_reference':'synthetic-fixture-only'})+'\n').encode())
        c=Controller.enroll(control,nonce_db,receipt);c.resume()
    return {'CARELINK_LEDGER_CONTROL_ROOT':str(control)}


def fixture_web_config(directory, nonce_db=None):
    directory = Path(directory)
    salt = "11" * 16
    values = {"CARELINK_AUTH_DATABASE_PATH":str(directory / "auth/web.sqlite3"),
              "CARELINK_WEB_ORIGINS":"https://testserver", "CARELINK_LOGIN_TEST_LIMIT":"100",
              "CARELINK_WEB_BOOTSTRAP_FILE":str(directory / "unused-missing-bootstrap.json")}
    values.update(fixture_device_control(directory,nonce_db))
    for username, variable in (("ttj", "CARELINK_PATIENT_PASSWORD_HASH"), ("wyn", "CARELINK_NURSE_PASSWORD_HASH")):
        digest = hashlib.pbkdf2_hmac("sha256", ("fixture-"+username+"-password-ONLY").encode(), bytes.fromhex(salt), 310000).hex()
        values[variable] = "pbkdf2_sha256$310000$"+salt+"$"+digest
    return values


def signing_client(base_client, directory):
    directory = Path(directory)
    registry = directory / "auth/devices.json"
    write_registry(registry)
    initialize_new_ledger(directory / "auth/nonces.sqlite3", authorization=AUTHORIZATION)
    os.environ["CARELINK_DEVICE_REGISTRY"] = str(registry)
    os.environ["CARELINK_DEVICE_NONCE_DB"] = str(directory / "auth/nonces.sqlite3")
    os.environ.update(fixture_web_config(directory))

    class SignedClient(base_client):
        def __init__(self, *args, **kwargs):
            kwargs.setdefault("base_url", "https://testserver")
            super().__init__(*args, **kwargs)

        def build_request(self, method, url, **kwargs):
            request = super().build_request(method, url, **kwargs)
            if method.upper() not in {"GET", "HEAD", "OPTIONS"} and request.url.path.startswith("/api/"):
                request.headers.update({"X-CareLink-CSRF":"1", "Content-Type":"application/json"})
            if method.upper() == "POST" and request.url.path == "/sensor-data":
                body = request.read()
                device = json.loads(body)["device_id"]
                request.headers.update(signed_headers(body, device))
            return request

    return SignedClient
