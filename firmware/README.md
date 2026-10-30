# ESP32 HTTPS/HMAC firmware

`elder_sensors/elder_sensors.ino` is the restored secure hardware source. It
preserves the analog pulse sensor, MLX90614, MPU6050, LCD and model-controlled
buzzer. The analog pulse sensor does not measure SpO₂.

Follow the root [README](../README.md) for the unified local gateway. After
`gateway:prepare`, `gateway:accounts` and `gateway:address`, manually open the
matching private sketch at
`.coursework/hardware-gateway/firmware/elder_sensors/elder_sensors.ino`.
Fill only its Wi-Fi placeholders locally. Its separate endpoint, device
credentials and CA headers match the new acceptance gateway. Never commit or
share these private headers. The public example headers contain placeholders.

Upload uses HTTPS `/sensor-data`, CA and server identity verification,
SNTP-synchronized time, API key, HMAC-SHA256 and random nonce. Failed time sync
or TLS validation must prevent upload; do not use `setInsecure()` or HTTP.
The gateway retains atomic nonce protection and guarded readings/alert writes.
Do not copy old device identity into a fresh ledger to bypass recovery checks.

The local compile check uses ESP32 Dev Module, Core Debug Level=None. Select
the actual board and USB port manually in Arduino IDE; Serial Monitor is
**115200 baud**. Observe Wi-Fi, time sync, sensor validity and repeated
`HTTPS POST status: 200`, then compare at least three advancing saved record
timestamps in both Web and Android. A build or HTTP 200 alone is not hardware
acceptance. No serial access or flashing is performed by the build checks.

```sh
npm run test:firmware
npm run check:firmware
```

The buzzer follows the model result returned by the authenticated upload. It
is off for invalid/missing data, malformed responses, network failures and
stale responses. Raw sensor thresholds do not independently activate it.
