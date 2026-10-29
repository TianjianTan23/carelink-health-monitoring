# CareLink native Android

The Android implementation uses Java and Android framework Views (no WebView). Minimum Android 8.0 / API 26; compile and target API 35. The app is 100% native and calls the existing Python REST API. Its screens cover readings, history, five-second charts, classifications with confidence explanations, alerts and settings. The header shows **only the current backend assessment** in large bold black text. Missing data shows a waiting state; expired abnormal assessments are marked as the last assessment.

## Install and connect

1. Start the shared backend with `../scripts/start-local-mac.sh` or the workspace's `start-carelink.command`.
2. Build/install the debug APK from `app/build/outputs/apk/debug/carelink-debug.apk` on an Android 8+ test device, or import this directory in Android Studio (JDK 17, Gradle 8.11.1, Android SDK 35, Build Tools 35.0.0).
3. In the app enter `http://10.0.2.2:8000` for the Android emulator; on a phone enter the Mac's LAN IP, e.g. `http://192.168.1.10:8000`. Keep the phone and Mac on the same network. Use the existing account passwords or set them with `npm run setup:accounts`; no passwords are displayed or stored on the phone.
4. Select Readings, History, Charts, AI, Alerts or Settings. Patient accounts only see their own data. Only the clinician role can acknowledge alerts. The current assessment stays above every page. Foreground updates run every five seconds and never overlap; network errors retain clearly dated historical values.

Both builds allow HTTP to local addresses. No certificate setup or installation is needed. If an older installation remembers an HTTPS URL, change the login address to HTTP. The supplied APK is debug-signed for coursework testing, not a Play Store release. Disable backup and keep passwords/cookies out of preferences and logs. Cookies are memory-only; reopening a destroyed process requires a new login.

## Architecture and verification

- `Models.java`: JSON decoding, timestamp and confidence validation.
- `ApiClient.java`: REST, memory-only cookies, request timeouts and patient/role checks.
- `MonitoringController.java`: asynchronous state updates, lifecycle polling and error recovery.
- `Monitoring.java`: current/held/stale display policy and median chart buckets.
- `MainActivity.java`, `TrendView.java`: native views and accessible chart summary, with no model inference in the UI.

Classification is performed by the shared saved LR model, CNN and safety logic on the backend. A confidence displayed for a safety rule is explicitly labelled as a rule indicator rather than a learned probability. Chart aggregation excludes held, invalid and duplicate beat samples. Storage and alert deduplication remain in backend SQLite.

The portable SDK build was used on this Mac because Android Studio was absent:

```sh
JAVA_HOME=/path/to/jdk17 ANDROID_HOME=/path/to/android-sdk sh build-apk.sh
JAVA_HOME=/path/to/jdk17 CARELINK_JSON_JAR=/path/to/json-20240303.jar sh test-core.sh
```

The `org.json` jar is needed only for host tests; Android supplies JSON decoding at runtime. Set `CARELINK_TEST_USER` and `CARELINK_TEST_PASSWORD` and pass a localhost base URL to `test-core.sh` to run real HTTP checks. Never commit credentials. Tests use seven synthetic backend fixtures, including missing readings, retained heart rates and a real CNN inference on the SisFall test window. Build and test logs are under `../review/verification-2026-10-29/`.

Hardware pulse accuracy, Wi-Fi latency and background notification delivery are not established by these tests. The app polls only while foregrounded; persistent server alerts can be reviewed after reopening.

## Historical device verification

The final HTTP APK has been rebuilt and its Java client tested against the actual HTTP backend; see `../review/http-delivery/RESULTS.md`. The emulator checks below were recorded during the initial Android integration, before the temporary HTTPS change, and have not been repeated for this build.

The APK was installed successfully on an isolated Android 15 arm64 emulator. 25 host core checks, 7 host HTTP checks, and 15 checks running inside Android passed. The Android checks exercise the native JSON decoder, real login/cookies, history/classification/alert endpoints, permission checks and offscreen Canvas rendering. See `tests/RuntimeChecks.java`; build the instrumentation APK with `tests/build-runtime-checks.sh` after building the app.

Native UI visual inspection was **not completed**: the desktop UI automation tool could not attach to the standalone emulator window. APK installation and these runtime checks are not a complete login/navigation visual demonstration. Please perform the phone walkthrough before submission. The web screenshot is labelled as web, not Android evidence.
