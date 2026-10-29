# CareLink Health Monitoring

CareLink is a coursework health-monitoring system with a native **Android app**, a React dashboard, a FastAPI/SQLite backend and ESP32 firmware. It monitors heart rate, temperature and falls. The page header displays **one current state** — NORMAL, WARNING or CRITICAL — in large bold black text, according to the backend assessment. Missing data is shown explicitly.

The current version uses **plain HTTP**. No HTTPS certificate, certificate installation, device API key, HMAC signature or NTP prerequisite is needed. Account passwords and role permissions remain in place. Existing local passwords are retained. Use this local-network coursework configuration with test data.

## Start on a Mac

```sh
npm start
```

The launcher installs dependencies when needed, retains existing account configuration (or asks for initial passwords), builds the web UI and starts the API on `0.0.0.0:8000`. Open **http://127.0.0.1:8000** on the Mac. Use this explicit HTTP address if your browser remembers the previous localhost HTTPS setting.

The account IDs are `ttj` (patient: own record) and `wyn` (caregiver: assigned records and alert acknowledgement). Initial passwords are entered privately in Terminal, stored only as salted hashes in ignored `.env`, and never embedded in the app. Set or change them with:

```sh
npm run setup:accounts
npm run setup:accounts -- --reset-passwords
```

Keep the API terminal running. On another device, use `http://<Mac-LAN-IP>:8000`; the phone, ESP32 and Mac must be on the same network. A new database has no readings until a producer sends data.

### Demonstrate without hardware

Double-click `start-without-hardware.command` (or `setup-and-demo.command` on a new clone). It starts the HTTP API and a separate synthetic producer, uses `backend/carelink-simulation.db`, labels the UI as simulated, and stops both processes with Control-C. It listens only on `127.0.0.1` and does not write into the hardware database.

For a separately running test API, a second terminal can send samples every second:

```sh
npm run simulate:sensors
# Or one selected scenario:
npm run simulate:sensors -- --scenario=warning --count=10
```

This exercises the actual LR, storage and alert path. The producer sends vital signs and a fall flag; it is not evidence of CNN recognition from a physical sensor. Real CNN motion-window inference is covered by integration tests.

## Android delivery

See [android/README.md](android/README.md). The app uses native Java and Android Views, requires Android 8.0+, and includes readings, history, five-second charts, AI results, alerts and settings. It uses the same API and role permissions as the web app. In the emulator enter `http://10.0.2.2:8000`; on a phone enter the Mac's LAN address. No CA installation is needed.

Build with Android Studio or the supplied SDK script:

```sh
JAVA_HOME=/path/to/jdk17 ANDROID_HOME=/path/to/android-sdk sh android/build-apk.sh
```

The debug APK is generated at `android/app/build/outputs/apk/debug/carelink-debug.apk`. Build output and signing keys are ignored by Git. Android is the required mobile submission; the optional iOS project is retained separately.

## Sensors and AI

Copy `firmware/elder_sensors/secrets.example.h` to ignored `secrets.h`, fill in Wi-Fi settings and the HTTP `/sensor-data` URL, then compile/upload the ESP32 sketch. Heart-rate acquisition runs in its own task targeting 500 Hz; motion acquisition targets 200 Hz. Snapshots upload every second. Valid observations form five-second median chart points; invalid/held values do not invent fresh measurements.

The saved LR classifier uses heart rate, temperature and the hardware fall flag. The SisFall CNN independently processes a two-second, six-axis motion window. A CNN fall score of at least 0.85 raises the final state to WARNING unless it is already CRITICAL. Explicit safety rules can also override the LR result. The CNN flag is not fed into LR as an extra feature. The UI identifies the source and meaning of confidence values.

## Project layout

- `android/`: required native Android application and tests.
- `src/`: React dashboard, live API client and chart/status presentation.
- `backend/`: HTTP API, accounts, roles, SQLite, alerts and integration tests.
- `sensor_core/`: packaged LR/CNN inference, trained weights, training scripts and evaluation evidence.
- `firmware/`: ESP32 sketch, pulse processor, motion sampling and signal tests.
- `ios/`: optional SwiftUI client; no signed IPA is included.
- [INTEGRATION.md](INTEGRATION.md): architecture, assignment traceability and measured limitations.
- [review/http-delivery/RESULTS.md](review/http-delivery/RESULTS.md): verification of this HTTP version.

## Development and tests

```sh
npm ci
npm run dev                 # HTTP web development server on port 5173
npm run start:api           # HTTP API on port 8000
npm test
npm run build
sh scripts/python-local.sh -m unittest backend.test_api backend.test_integration backend.test_security backend.test_accounts backend.test_http -v
```

The real-network Python suite also runs Android Java interoperability when `JAVA_HOME` and `CARELINK_JSON_JAR` are provided; otherwise that item is explicitly skipped. A standalone clone uses packaged models and creates its own `.venv`; it does not require the parent `elder-sensors` workspace or SisFall training directory. Node 22.19+ and a Python version compatible with `backend/requirements.txt` are required.

The original Git history is retained. Private `.env`, Wi-Fi credentials, certificates, keys, databases and generated build directories are excluded from Git.
