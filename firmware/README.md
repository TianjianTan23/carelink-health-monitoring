# ESP32 firmware

`elder_sensors/elder_sensors.ino` reads the heart-rate sensor, MLX90614 temperature sensor and MPU6050 fall detector, updates the LCD1602A, and posts each snapshot to FastAPI.

Before compiling:

1. Copy `elder_sensors/secrets.example.h` to `elder_sensors/secrets.h`.
2. Enter the 2.4 GHz Wi-Fi name/password and the Mac's current LAN or hotspot IP.
3. Start FastAPI on `0.0.0.0:8000`.

Each Mac has its own LAN address. Run `npm start` in the repository root and
use the printed `ESP32 upload URL`; do not copy another team member's IP. The
web page automatically requests the latest backend record once per second,
but it can only change when the API Terminal is receiving repeated
`POST /sensor-data` requests.

The buzzer has one authority: the model result returned by `POST /sensor-data`. It sounds only while the most recent valid server classification is `warning` or `critical`. It is explicitly off for `normal`, invalid/missing data, malformed responses, network failures, and stale responses. Raw sensor thresholds do not activate it independently.
