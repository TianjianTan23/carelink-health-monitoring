# CareLink API

This FastAPI service receives the existing ESP32 JSON at `POST /sensor-data`, stores readings and model outputs in SQLite, and exposes authenticated `/api/*` routes to the React app.

Local coursework accounts:

- Patient: `ttj` / `041003`
- Nurse: `wyn` / `050403`

These plaintext demonstration credentials are intentionally local-only and must be replaced with hashed passwords and a real identity provider before deployment.

Run from the repository root:

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
.venv/bin/python -m uvicorn backend.app:app --host 0.0.0.0 --port 8000
```

The SQLite database is created at `backend/carelink.db`. Override it with `CARELINK_DATABASE_PATH`.
