# Integrated CareLink application — 29 October 2026

This checkout combines the GitHub CareLink UI with the existing elder-sensors LR/CNN implementation. The upstream revision is `1592530fe49dac7883d99e9cfd32a3b256d8114e`; its four existing commits are retained. This integration retains that history; the team must document its own individual contributions separately. The delivered configuration uses HTTP without certificates or device signing. Current regression results are in `review/http-delivery/RESULTS.md`.

## Run the application

From the parent `elder-sensors` directory, double-click `start-carelink.command`, or run:

```sh
cd carelink
npm start
```

Visit `http://127.0.0.1:8000`. This starts `backend.app:app`, which serves the React build and authenticated API. The older `server/app.py` remains a diagnostic server; it is not the new CareLink application. Do not run both services on port 8000. The launcher retains existing account passwords or prompts for initial passwords; the role comes from the server. Preferences persist in the browser, and an existing unexpired session is restored on reload.

The integrated workspace reuses `../server/.venv`. A standalone copy of `carelink/` creates its own `.venv` and installs `backend/requirements.txt`. Python must support the pinned packages. The `sensor_core/` package contains both model artifacts, preprocessing metadata, training scripts, evaluation evidence and test fixtures. `npm run sync:sensors` updates those files and the firmware from the parent workspace when present; it never copies Wi-Fi credentials, databases or compiled firmware. Existing parent `server/sensor_data.db` records are preserved, but are not automatically mixed into the new `backend/carelink.db`.

To supply explicit synthetic coursework readings:

```sh
npm run simulate:sensors
```

This separate producer posts through the API, trained model, storage and alert system; the UI does not invent readings or silently switch to mock mode when the network fails.

## KY-039 acquisition and display

The sensor is an infrared LED/phototransistor pair: the ESP32 reads an optical voltage waveform, then estimates BPM from pulse intervals. It does not output a ready-made heart rate. Joy-IT explains the weak signal, ambient-light sensitivity and importance of placement in its [KY-039 documentation](https://sensorkit.joy-it.net/en/sensors/ky-039).

The new `heart_rate_processor.h` is used by a dedicated FreeRTOS task with a target interval of 2 ms (500 samples/s), independent of LCD updates, I2C temperature reads, JSON serialization and Wi-Fi. Non-overlapping 20 ms means reduce 50 Hz interference; baseline removal and filtering expose the pulse waveform. Hysteresis and a refractory interval reject duplicate detections. A three-interval median and modest smoothing reduce isolated jitter. Two consistent new intervals allow a sustained rate change to be followed instead of being rejected indefinitely. Fixed DC contact thresholds and invented half-interval recovery have been removed.

New BPM values are produced on accepted beats, after enough pulses have arrived. Firmware uploads snapshots every second. The packet includes sample/gap counters and signal state for timing diagnostics. These are configured rates; they must still be measured on the physical board under load.

Both interfaces retain a last valid heart rate for up to 30 seconds, labelled with its age, during brief signal loss. This number is never supplied to LR and never inserted as a fresh chart measurement. At startup, or after expiry, the interface shows acquisition/unavailable status rather than fabricating a number. No algorithm can guarantee a valid BPM continuously without a usable optical signal.

Charts show the latest ten minutes and one median of valid observations per completed 5-second interval. Repeated uploads of the same accepted beat are deduplicated. Missing intervals remain gaps. Historical samples do not disappear just because the device later disconnects. Web readings poll once per second; heavier resources and native foreground updates use five-second intervals. Slow requests are coalesced so a one-second timer cannot continually discard a valid but slower response.

Flash the current `esp32/elder_sensors/elder_sensors.ino` in the parent workspace, using its private `secrets.h`, or use the synchronized `firmware/elder_sensors` copy with your own `secrets.h`. Set `SERVER_URL` to `http://<computer-LAN-IP>:8000/sensor-data`. The sketch was compiled but was not flashed during this task. No human measurements were collected for validation.

## Classification and visible status

The fixed status header displays **only one current assessment**: NORMAL, WARNING or CRITICAL, based on the backend AI/fusion result. Text is large, black and bold; colour is an additional cue. Web charts measure their container width so axes remain readable on phone-width displays. Missing or stale normal data shows WAITING FOR DATA instead. A previously abnormal assessment is retained with an explicit stale/last-assessment message. Historical pages may still list past labels alongside their timestamps.

The backend uses the existing LR classifier and explicit safety overrides. A separate SisFall CNN analyzes a validated two-second, six-axis motion window. A CNN fall score of at least 0.85 raises the final state to WARNING unless it is already CRITICAL. It does not become LR's hardware `fall` input. The UI distinguishes LR class probabilities, CNN fall scores and deterministic safety-rule indicators. The source model and reasons are retained in saved predictions. Raw 400-sample motion windows are not stored in every database row.

## Required Android application

The user confirmed that the mobile submission must be Android. `android/` is now the main mobile deliverable: native Java/Android Views with a separate data model, API client, asynchronous controller and presentation policy. It includes both roles, real login, live readings, five-second median charts, classifications and confidence, stored alert history, caregiver acknowledgement and persistent settings. Passwords are not stored. Both builds support local HTTP addresses; no certificate installation is required.

A debug APK has been compiled and its v2/v3 signatures verified at `android/app/build/outputs/apk/debug/carelink-debug.apk`. Minimum Android version is 8.0 (API 26); compile/target API is 35. See `android/README.md` for Android Studio and portable command-line build instructions. Twenty-five Android core checks and seven additional actual HTTP checks passed. Installation succeeded on an isolated Android 15 emulator, and 15 native instrumentation checks passed, including actual Android HTTP/cookies, model JSON, scope enforcement and offscreen Canvas drawing. Native UI visual inspection was not completed because the desktop UI tool could not attach to the standalone emulator window; a physical phone demonstration remains outstanding. The instructor's approval of the chosen native Android framework remains a course-specific requirement.

The fixed mobile header shows only the current assessment, with large bold black text. On valid data the backend classification controls NORMAL/WARNING/CRITICAL; no client-side thresholds recreate the LR model. A missing classification is not converted to NORMAL. CNN suspicion is also shown explicitly on the fall card, separate from a hardware-reported fall.

## Optional legacy iPhone application

Open `ios/CareLink.xcodeproj` in full Xcode. The native app now signs in through the real API, uses the returned account role, decodes the actual heart-rate/temperature/fall contract without requiring SpO2, polls while foregrounded, and provides patient and caregiver access to charts, history, classifications, confidence explanations and settings. Only caregivers can acknowledge alerts. `DemoStore` acts as the view model; SwiftUI views use it, and `CareService`/`LiveApiService` isolate transport and decoding.

Enter the computer's LAN address on the iPhone login screen. `localhost` is suitable only for a simulator running on that computer. Local-network usage is declared in `LocalNetwork.plist`; the optional coursework client permits HTTP for the configured local server. Passwords are sent only to the configured API and are not saved by the app; URLSession's session cookie is held in memory.

Full Xcode and an iOS SDK are absent on this machine. Foundation tests, actual URLSession HTTP checks and Swift syntax parsing passed; they do **not** prove that the SwiftUI target compiles or runs. This optional iPhone project is not the required Android submission. A responsive website alone does not satisfy the assessment; use the Android source and APK above.

## Assessment traceability

| Assessment requirement | Implementation/evidence | Remaining qualification |
|---|---|---|
| Functioning installable Android app | Native APK compiled, signature verified, installed on Android 15; 15 native runtime checks passed | Native UI visual inspection and physical phone demonstration still required |
| Two introductory classifiers, saved selected model | LR/RF training and evaluation in `sensor_core/ml` | Original metrics are synthetic-data results; both improved models tied; hidden assessment set not supplied |
| JSON classification and confidence endpoint | Authenticated `/api/classify`; `/sensor-data` integrates CNN | Plain HTTP JSON ingestion; no device signature or certificate is required |
| Patient and caregiver readings, history, charts, classifications and settings | React and native Android screens, with API-enforced role scope | Physical phone accessibility and usability review still required |
| Storage, alert history and duplicate prevention | SQLite; one unresolved episode per patient/condition; caregiver acknowledgement | Existing legacy DB is separate and unchanged |
| Missing/invalid/network-failure handling | Flag/age validation, held-value separation, persisted connectivity alerts, retained timestamped data | Physical-network latency not measured |
| Authentication and role access | Server password hashes and HttpOnly cookie; patient-scope and caregiver checks | Password hashes, revocable server sessions, CSRF and login limits remain; HTTP transport is unencrypted |
| Accessible consistent status cues | One current state in large bold black text, unknown/stale cues, labels and navigation | Android TalkBack and large-font testing on a physical device still outstanding |
| Justified architecture | Native view-model-service layers; React components/data services; backend adapter and shared model runtime | Architecture diagrams and full technical report are separate submission work |
| Git evidence | Original history retained; current source changes visible in Git | Individual contribution evidence remains a team responsibility |
| Test scenarios and improvement | API, UI, Swift, pulse replay and before/after measurements below | No invented clinical, hidden-test or hardware performance claims |
| Educational prototype notice | Displayed in web/native application | Demonstrate with supplied synthetic or otherwise approved anonymised data, per brief |

## Reproducible checks and historical integration measurements

The following performance numbers and device checks were recorded during the initial integration. They are not fresh measurements of the final account/HTTP changes. See `review/http-delivery/RESULTS.md` for the final regression run.

```sh
npm test
npm run build
../server/.venv/bin/python -m unittest backend.test_api backend.test_integration -v
npm run test:ios-core
c++ -std=c++17 firmware/tests/heart_rate_test.cpp -o /tmp/carelink-heart-test
/tmp/carelink-heart-test
c++ -std=c++17 firmware/tests/heart_before_after.cpp -o /tmp/carelink-heart-comparison
/tmp/carelink-heart-comparison
/tmp/carelink-heart-comparison low
```

This Mac's default Command Line Tools SDK does not match its compiler. Host checks used the installed compatible SDK: `CARELINK_MACOS_SDK=/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk` for Swift; `-isysroot /Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk` for C++. This does not provide an iOS SDK.

| Check | Original GitHub checkout | Integrated version |
|---|---:|---:|
| Node tests | 19 passed | 19 passed |
| React/data tests | 27 passed | 35 passed |
| API integration tests | 6 passed | 18 passed |
| Android core + real HTTP checks | No Android client in upstream | 25 core + 7 HTTP passed |
| Android emulator runtime | No Android client in upstream | APK installed; 15 native runtime checks passed; no native UI visual inspection |
| Swift Foundation checks | Unchanged upstream suite not verified on this host | 127 passed |
| KY-039 synthetic waveform checks | No dedicated harness | 20 passed |

For the synthetic waveform comparison, both processors received the same 500 Hz inputs: a 75 BPM sine wave with 50 Hz interference, then a step to 120 BPM. At a DC level of 2200 ADC counts, first output improved from 2.042 s to 1.662 s. The new processor followed the new rate within 1.182 s; the baseline did not reach within 5 BPM during the following 10 s. At a DC level of 1000, the baseline produced no BPM because of its fixed contact threshold; the new processor acquired in 1.662 s. Stable-period mean absolute errors were 0.103 BPM (baseline) and 0.127 BPM (new). Thus the demonstrated improvements are acquisition and recovery, **not** an established improvement in absolute accuracy. These waveforms are not recordings from a person or the physical sensor.

Thirty warmed in-process API calls per scenario yielded baseline/new median response times of 3.346/3.439 ms (normal), 3.337/3.243 ms (warning) and 3.277/3.336 ms (critical). The new CNN-warning path had a median of 5.380 ms and a 95th percentile of 5.780 ms. This includes request handling and SQLite, but excludes real networking.

An additional 30-request loopback HTTP measurement gave a POST median of 3.950 ms (p95 4.414 ms). Time from submitting a critical synthetic reading to retrieving its stored alert was 6.482 ms median (p95 7.479 ms). This is server/loopback alert visibility, not sensor-to-phone latency. Web/native polling adds up to approximately 1/5 seconds under normal foreground operation; Wi-Fi, scheduling, sensor acquisition and user-visible alert latency still need device measurement.

ESP32 compilation succeeded: 993,360 bytes flash (75%) and 73,792 bytes static RAM (22%). The configured 500 Hz acquisition rate and performance on a physical KY-039 have not yet been verified. Detailed logs and JSON measurements are in `review/verification-2026-10-29/`.
