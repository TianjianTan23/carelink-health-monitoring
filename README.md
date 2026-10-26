# CareLink Health Monitoring

CareLink now combines the ESP32 sensor stream, SQLite storage, a trained classifier, rule-based abnormal-parameter attribution, authenticated role views, alert history, and a React dashboard.

The active monitoring scope is deliberately limited to the three signals that the hardware actually supplies:

- heart rate
- temperature
- fall detection

SpO2 is not displayed or used for classification in the new React/FastAPI flow.

## Local accounts

These are coursework-only local accounts. The selected role comes from the account on the server; it cannot be chosen in the browser.

| Role | ID | Access |
| --- | --- | --- |
| Patient | Provided separately | Own patient record only; cannot acknowledge alerts |
| Nurse | Provided separately | Assigned patients; may acknowledge alerts |

The login page does not display or prefill credentials, and the password input cannot be switched to plain text. The FastAPI service stores only salted PBKDF2-SHA256 password hashes; override them with `CARELINK_PATIENT_PASSWORD_HASH` and `CARELINK_NURSE_PASSWORD_HASH` when accounts change.

Both roles can view readings, history, charts, classifications, confidence, abnormal parameters, alert history, and settings. The patient page is scoped to the signed-in patient's own data.

## Run the complete live system on macOS

The checked-in configuration uses `live` mode. It does not load the mock
patients or generate changing values in the browser. From a fresh clone, run:

```sh
npm start
```

This single command creates `.venv` when necessary, installs the Python and
Node dependencies, builds the React UI, and starts FastAPI on
`0.0.0.0:8000`. Keep that Terminal window open and visit:

```text
http://127.0.0.1:8000
```

The dashboard requests fresh API data every second with browser caching
disabled. A new clone starts with an empty SQLite database, so values cannot
change until a sensor producer posts snapshots to `/sensor-data`.

### Verify real-time updates without hardware

The coursework permits synthetic sensor data. In a second Terminal window,
run this separate input tool to exercise the real FastAPI, trained model,
SQLite tables, alert logic and live UI:

```sh
npm run simulate:sensors
```

It cycles through normal, warning and critical readings once per second. Stop
it with `Ctrl+C`. This is an explicit test producer; the UI and backend remain
in live mode. You can also select one state:

```sh
npm run simulate:sensors -- --scenario=normal
npm run simulate:sensors -- --scenario=warning
npm run simulate:sensors -- --scenario=critical
```

### Connect the physical ESP32

Copy `firmware/elder_sensors/secrets.example.h` to the ignored `secrets.h`,
then set `SERVER_URL` to the LAN IP printed by `npm start`. The URL must end in
`/sensor-data`. Recompile and upload the sketch whenever the gateway Mac or
network changes.

Before opening the UI, verify that the API is running:

```sh
curl http://127.0.0.1:8000/health
```

Then watch the API Terminal while the ESP32 is running. It must receive a new
`POST /sensor-data` repeatedly. If no POST arrives, the UI correctly retains
the last SQLite record and eventually marks it stale; it must not invent new
measurements.

### Manual development setup

From this repository directory, install and start the API:

```sh
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
.venv/bin/python -m uvicorn backend.app:app --host 0.0.0.0 --port 8000
```

In a second Terminal window, install and start the React development UI with
hot reload:

```sh
npm ci
npm run dev
```

Open [http://127.0.0.1:5173](http://127.0.0.1:5173). Vite forwards `/api`, `/sensor-data`, and `/health` to the FastAPI process on port 8000.

The one-command `npm start` path above is the preferred production-style local
run. Its underlying manual commands are:

```sh
npm run build
.venv/bin/python -m uvicorn backend.app:app --host 0.0.0.0 --port 8000
```

Then open [http://127.0.0.1:8000](http://127.0.0.1:8000). FastAPI serves the generated React build as well as the API.

If another older sensor server is already using port 8000, stop it before
starting this API. The ESP32 and the computer must be on the same network, and
the ESP32 upload URL must be `http://<Mac-LAN-IP>:8000/sensor-data`;
`127.0.0.1` only works from the Mac itself. Each team member has a different
LAN IP, so copying another member's `secrets.h` will not work.

## Sensor input

The ESP32 continues to post a JSON snapshot to:

```text
POST /sensor-data
```

The backend accepts the existing nested or top-level forms for:

- `heart_rate_bpm`, `heart_rate_display_bpm`, or `heart_rate.bpm`
- `object_temp_c`, `mlx90614.object_temp_c`, or `temperature`
- `fall_detected`, `mpu6050.fall_detected`, or `alarm`

Each accepted snapshot is saved in the SQLite `readings` table. The dashboard retrieves the current reading, full 24-hour history, and the heart-rate and temperature chart series from this table.

The corresponding Arduino sketch is in `firmware/elder_sensors`. Its buzzer follows only the backend model result: `warning` and `critical` sound the buzzer; every other state turns it off. Copy `secrets.example.h` to the ignored `secrets.h` and enter the Mac's current local address before compiling.

## Classification and attribution

For a complete, physically valid sample, the trained logistic-regression artifact at `backend/ml/artifacts/health_classifier.joblib` supplies:

- `label`: exactly `normal`, `warning`, or `critical`
- `confidence`: the probability assigned to the selected model class

A separate rule-based attribution layer supplies `abnormal_params`. It explains which observed parameter is abnormal without replacing the model's combined classification. For example:

```json
{
  "label": "critical",
  "confidence": 0.97,
  "abnormal_params": [
    {"parameter": "fall_detected", "value": true, "reason": "A fall was detected."}
  ]
}
```

Missing or physically invalid data is never sent through the classifier and is never replaced by a made-up value. In that case `label` and `confidence` are `null`, `validation_errors` describes the problem, and a data-quality alert is stored.

## Alerts and SQLite

The default database file is `backend/carelink.db`. Set `CARELINK_DATABASE_PATH` to use another path.

The database contains:

- `readings`: raw snapshots, validated values, model output, attribution, and timestamps
- `alerts`: clinical, missing-data, invalid-reading, and network-failure alerts

A partial unique index prevents more than one unresolved alert for the same patient and condition. Repeated occurrences update the existing alert and increment `occurrence_count`. When a later reading clears the condition, the unresolved alert is marked resolved instead of silently disappearing.

## API summary

- `POST /api/login`, `POST /api/logout`, `GET /api/session`
- `GET /api/patients`, `GET /api/patients/{patient_id}`
- `GET /api/patients/{patient_id}/readings?minutes=1440`
- `GET /api/patients/{patient_id}/predictions`
- `GET /api/alerts`
- `POST /api/alerts/{alert_id}/acknowledgement`
- `POST /api/classify`
- `POST /sensor-data`
- `GET /health`

Authentication uses an HttpOnly local session cookie. Authorization is enforced again on the API, so hiding a button is not the only protection.

## Verification

```sh
npm test
npm run build
.venv/bin/python -m unittest backend.test_api -v
```

The automated checks cover both account roles, route visibility, chart/history rendering, no-SpO2 rendering, model output and rule attribution, invalid/missing data, alert deduplication, network-failure alerts, and nurse-only acknowledgement.

## Deployment note

The two local accounts are suitable only for this coursework demonstration. Before any real deployment, use HTTPS, add a persistent session/identity provider, rotate credentials and the session secret, and perform a clinical and privacy review. This project is not a medical device.
