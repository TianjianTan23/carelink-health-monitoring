# CareLink — ESP32, Mac gateway, Web and Android

CareLink receives real sensor data from an ESP32, stores readings and alerts in a local FastAPI/SQLite gateway, and shows the same patient data in a Web dashboard and an Android app. This repository contains the complete application source, dependency locks, Android Gradle wrapper, firmware source, public configuration examples, tests, and a signed Android APK. The iOS source is retained. Private identities and the currently running database are backed up **locally only**; they are deliberately absent from GitHub.

## System layout

```text
ESP32 pulse/MLX90614/MPU6050 → HTTPS + HMAC /sensor-data → Mac FastAPI gateway
                                                        ├→ SQLite readings and alerts
                                                        ├→ Web dashboard (same HTTPS origin)
                                                        └→ Android native HTTPS client
```

- `backend/`: FastAPI routes, authentication, model, durable nonce ledger and write control.
- `src/`, `public/`, `shared/`, `models/`: React/Vite Web interface and shared data contracts.
- `android/`: Capacitor Android project with a native OkHttp API plugin and Keystore session vault.
- `firmware/elder_sensors/`: ESP32 sketch, signing logic and **placeholder** headers. The analog pulse sensor does not measure SpO₂; missing SpO₂ is shown as unavailable.
- `ios/`: retained iOS source; current end-to-end hardware verification is for Web and Android.
- `releases/CareLink-Android-release.apk`: signed installable Android build for the current gateway CA. The signing identity stays local; building from a new clone creates a different signing identity, so it cannot update this APK in place.
- `API_CONTRACT.md`: API and data behavior.

## Run a fresh, independent system

Requirements: Node.js 22.19+, Python 3.11/3.12, OpenSSL, Android JDK 21 + SDK 36 for rebuilding the APK, and Arduino IDE/CLI with the ESP32 core and sketch libraries for hardware. On a fresh machine, run from the repository root:

```sh
npm ci
python3.12 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-demo.txt
npm run build
npm run gateway:prepare -- --confirm-new-identity
npm run gateway:accounts
npm run gateway:address -- --lan-ip YOUR_MAC_LAN_IP --confirm-service-stopped
npm run gateway:check
npm run gateway:start
```

`gateway:prepare` creates a **new** device identity, HMAC secret, root CA, account store, readings database and nonce ledger in ignored `.coursework/hardware-gateway/`. Run it only for a genuinely new installation; it refuses an existing directory. `gateway:accounts` prompts for local account passwords without printing them. Replace `YOUR_MAC_LAN_IP` with the Mac address visible to the phone and ESP32. `gateway:address` requires the gateway to be stopped and updates the server certificate and generated firmware endpoint without resetting the ledger. The gateway serves Web and API together on HTTPS port 19443. Verify it with:

```sh
curl --cacert .coursework/hardware-gateway/tls/root.crt https://localhost:19443/health
```

For the ESP32, open `.coursework/hardware-gateway/firmware/elder_sensors/elder_sensors.ino`, fill the **local** `secrets.h` Wi-Fi placeholders, choose the actual board and port, then flash with Arduino IDE. This generated private sketch carries matching device credentials, gateway endpoint and public CA. Observe `HTTPS POST status: 200` at 115200 baud and confirm advancing readings in both clients. Never use the example credential headers as a real identity.

For Android, install the included APK or build one with `npm run android:apk` (set `JAVA_HOME` and `ANDROID_HOME` if needed). Enter `https://YOUR_MAC_LAN_IP:19443` in the app. Import the matching public `.coursework/hardware-gateway/tls/root.crt` as a user CA on the phone, or build a new APK with the matching public CA in `android/app/src/main/res/raw/carelink_gateway_ca.crt`. The certificate must include the API address in its SAN; TLS verification remains enabled. With ADB over USB, `adb reverse tcp:19443 tcp:19443` permits the app's explicit `https://127.0.0.1:19443` endpoint. Keep the reverse mapping active while testing. The included APK has the CA of the current installation, so a fresh gateway with a different CA needs its own CA trust setup. Web access uses `https://YOUR_MAC_LAN_IP:19443/`.

`npm run android:apk` writes `.coursework/deliverables/CareLink-integrated-release.apk`. Keep `.coursework/signing/` private if you want later APKs to update an existing installation. A different signing key requires a separate install; back up app data first if it matters.

## Encryption and security design (for the group report)

| Layer | Implementation | What it protects |
|---|---|---|
| Transport | HTTPS/TLS from ESP32, Web and Android to the Mac gateway; CA chain, expiry and host/IP SAN checks remain enabled. Android denies cleartext traffic. | Readings, passwords and sessions in transit; helps detect a forged gateway. |
| Android session at rest | The native `SessionVault` encrypts the opaque session token with AES-GCM using an Android Keystore key. The nonce/IV and ciphertext are kept in private app preferences; the key is not exported to JavaScript. | The stored session token on the phone. |
| Password storage | The server stores Argon2id hashes with per-password salt and bounded verification work. Older PBKDF2-SHA256 hashes migrate on a successful login. | Password verification without storing plaintext passwords. **Hashing is not reversible encryption.** |
| Browser/session boundary | The gateway issues an opaque, revocable 8-hour session token in a `Secure`, `HttpOnly`, `SameSite=Lax` cookie. Only a token hash is stored server-side. Web requests use same-origin checks; mutating JSON requests require `X-CareLink-CSRF: 1`. | Session misuse and cross-site request forgery. |
| Android request boundary | The native OkHttp client uses `CookieJar.NO_COOKIES`, stores the cookie only in its Keystore-backed vault, and does not expose token or response headers to the WebView. It sends the CSRF header on POST and rejects redirects and non-HTTPS API origins. | Accidental token copying into WebView storage and insecure API routing. |
| ESP32 device authentication | Each POST signs a seven-line canonical request with HMAC-SHA256 over method, path, device ID, timestamp, random nonce and SHA-256 body digest. The gateway checks the API key, signature and a ±60-second timestamp window. | Forged or modified uploads. HMAC authenticates the request; it does **not** encrypt it. TLS supplies confidentiality. |
| Replay protection | A durable SQLite nonce ledger reserves each accepted nonce, then guarded writes commit readings and alerts. Replayed nonces are rejected; missing/corrupt ledger state fails closed. | Duplicate uploads and replay attacks across restarts. |

Relevant implementation: `backend/web_auth.py`, `backend/web_security.py`, `backend/device_auth.py`, `backend/nonce_ledger.py`, `backend/ledger_control.py`, `android/app/src/main/java/com/carelink/coursework/SessionVault.java`, `CareLinkApiPlugin.java`, `android/app/src/main/res/xml/network_security_config.xml`, and `firmware/elder_sensors/device_signing.h`.

**Scope limit:** the gateway's SQLite files are not encrypted at rest by this code. Their protection depends on local filesystem permissions and the Mac's disk encryption. The `.coursework/hardware-gateway/` directory contains live account hashes, readings, private keys, device credentials and nonce state and must never be posted to GitHub. Likewise, `firmware/**/secrets.h`, `device_auth.h`, `gateway_ca.h`, `.secrets/`, `.coursework/signing/`, APK signing keystores and private CA keys are excluded. The bundled Android CA certificate is public, not a private key.

## Current behavior and checks

The real sensor normally uploads about once per second. Heart rate needs a stable pulse signal; the interface retains the most recent valid value for up to six seconds while contact is plausible, then shows the missing-value dash if no valid measurement arrives. History requests allow the larger real response size and refresh periodically. A value must still come from an actual saved reading. The current firmware uses an analog pulse sensor, MLX90614 and MPU6050; it does not produce genuine SpO₂.

```sh
npm test
npm run build
.venv/bin/python -m unittest backend.test_local_gateway -v
npm run test:firmware
npm run check:firmware
npm run android:apk
```

`npm run check:firmware` is a compilation check with synthetic headers, not a physical upload. `npm run test:local-integration` additionally requires a configured Android emulator and local ports; it uses isolated test identities. Real-hardware validation requires an ESP32 and a phone on a reachable network or the ADB USB reverse route for the phone. `/health` alone only proves the gateway is running.

## Packaging and restoration

The GitHub branch and source ZIP include everything needed to **build and provision a new running system**, plus the current signed APK. Install dependencies and create a new private gateway as above. The ZIP does not carry `node_modules`, SDK/JDK, generated build caches or live private state. These are either reinstallable or unsafe to publish. The current installation's state has a separate local-only backup; recovering that exact identity requires its CA keys, device registry, account database, readings database and nonce/control state together. Do not initialize a fresh ledger against old device credentials or restore only one SQLite file. Stop writes and follow a coordinated restore procedure before using that backup; the online backup is a point-in-time copy per database, not an atomic snapshot across all files.
