# CareLink API

FastAPI accepts HTTP JSON at `POST /sensor-data`, runs the packaged LR/CNN and fusion policy, stores readings in SQLite, and exposes authenticated `/api/*` routes to web and mobile clients. Sensor ingestion does not require device signatures or certificates.

From the repository root run `npm start`, or `npm run setup:accounts` followed by `npm run start:api`. Existing local passwords are retained. Accounts use salted Argon2id hashes, opaque server sessions, CSRF and role/patient scope checks. HTTP cookies work on the local network; no TLS configuration is needed.

The default database is `backend/carelink.db`; `CARELINK_DATABASE_PATH` overrides it. The hardware-free launcher uses a separate simulation database and labels simulated input. Missing or stale data is never silently classified as normal.

See the root README and INTEGRATION.md for startup, model behavior and limitations.
