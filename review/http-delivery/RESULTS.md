# HTTP delivery verification — 29 October 2026

The delivered system uses plain HTTP for the Mac gateway, web dashboard, Android app and ESP32. Mandatory TLS, CA setup/trust scripts, device API keys, HMAC signing and NTP prerequisites were removed. Account passwords, session revocation, CSRF and role/patient permissions remain. Existing local passwords were preserved.

The CNN/LR runtime, trained weights, continuous pulse/motion tasks, five-second chart buckets and one-current-status UI remain part of the integration.

| Verification | Result |
|---|---|
| Backend API + CNN integration + account/session checks | 31 tests passed |
| Real HTTP interoperability + account setup | 6 tests passed, none skipped; includes native Java client, Node producer and isolated demo process cleanup |
| Web | 19 Node and 36 React/data tests passed, including real HTTP fixture |
| Production web build | TypeScript and Vite passed |
| Native Android | APK compiled; v2/v3 signature verification passed; native Java login/cookie/data/scope/logout interoperability passed over actual HTTP |
| ESP32 | Compiled with placeholder Wi-Fi settings; 993,516 bytes flash (75%), 73,792 bytes static RAM (22%) |
| KY-039 synthetic waveform regression | 20 checks passed |
| Optional Swift client | 128 Foundation/data checks passed; no full iOS SDK build |
| Local credential exact-match scan | Zero matches in shareable files and Git history; secret values not displayed |
| Whitespace check | git diff --check passed |

Commands used the existing Python environment, local JDK 17/Android SDK 35 and host org.json test dependency. The current account-check command succeeded without changing stored passwords. Firmware compilation used placeholders and did not flash hardware. The Android APK was rebuilt after restoring cleartext access and removing the CA policy.

Run the backend checks with:

```sh
JAVA_HOME=/path/to/jdk17 CARELINK_JSON_JAR=/path/to/json.jar \
  sh scripts/python-local.sh -m unittest backend.test_api backend.test_integration backend.test_security backend.test_accounts backend.test_http -v
```

Without the Java environment variables, the Java interoperability test is explicitly skipped. The test suite uses generated temporary passwords and separate temporary databases, not real user credentials.

The historical emulator installation/runtime checks under `../verification-2026-10-29/` predate this final HTTP package. They have not been repeated for this APK; current evidence establishes compilation, signature validity and host Java HTTP interoperability. Physical-phone UI, actual ESP32 timing, sensor accuracy and real-network latency remain unverified. No clinical performance claim is made.

Fresh clones require account password setup but no certificates or device credentials. `npm start` uses the packaged model runtime when no parent sensor workspace exists. The private local `.env`, Wi-Fi header, old unused certificates/keys, SQLite databases and build products remain excluded from Git.

Current debug APK SHA-256: `3a65cd0abd8fabbf7ed83cf07054b2572bfb88332076f4e501c44f8ae2f7eae2`.
