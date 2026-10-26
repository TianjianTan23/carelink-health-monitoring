# CareLink API

This FastAPI service receives the existing ESP32 JSON at `POST /sensor-data`, stores readings and model outputs in SQLite, and exposes authenticated `/api/*` routes to the React app.

Local coursework account IDs and passwords are supplied separately and are not shown in the UI or documentation. Passwords are verified against salted PBKDF2-SHA256 hashes. Set `CARELINK_PATIENT_PASSWORD_HASH` and `CARELINK_NURSE_PASSWORD_HASH` to rotate them without editing source code.

Run from the repository root:

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
.venv/bin/python -m uvicorn backend.app:app --host 0.0.0.0 --port 8000
```

The SQLite database is created at `backend/carelink.db`. Override it with `CARELINK_DATABASE_PATH`.
