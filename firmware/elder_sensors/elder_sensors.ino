#include "heart_rate_processor.h"
#include <Wire.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <ArduinoJson.h>
#include <math.h>
#include <WiFi.h>
#include <WiFiClient.h>
#include <HTTPClient.h>

#include "secrets.h"
#include "motion_stream.h"

// Allow enough time for the Mac-hosted FastAPI classifier to respond.
const uint32_t HTTP_TIMEOUT_MS = 15000;
const int MPU_SDA = 21;
const int MPU_SCL = 22;
const uint8_t MLX_ADDRESS = 0x5A;
const uint8_t LCD_COLUMNS = 16;
const int LCD_RS_PIN = 13;
const int LCD_ENABLE_PIN = 14;
const int LCD_D4_PIN = 16;
const int LCD_D5_PIN = 17;
const int LCD_D6_PIN = 18;
const int LCD_D7_PIN = 19;
const int HEART_RATE_PIN = 34;  // Analog S pin; ADC1 works while WiFi is active.
const int BUZZER_PIN = 25;      // S pin of an active-high buzzer module.
const char *DEVICE_ID = "esp32-01";
const char *PATIENT_ID = "patient-01";

// Fall detector thresholds. Total acceleration includes gravity, so a stable
// device is close to 1g. A fall must pass multiple phases to reject bumps.
const float FREE_FALL_THRESHOLD_G = 0.50f;
const float IMPACT_THRESHOLD_G = 2.50f;
const float STRONG_IMPACT_THRESHOLD_G = 3.50f;
const float STILL_MIN_G = 0.75f;
const float STILL_MAX_G = 1.25f;
const float POSTURE_CHANGE_DEGREES = 45.0f;
const unsigned long FREE_FALL_CONFIRM_MS = 120;
const unsigned long IMPACT_WINDOW_MS = 1200;
const unsigned long POST_IMPACT_SETTLE_MS = 300;
const unsigned long POST_IMPACT_TIMEOUT_MS = 2200;
const unsigned long FALL_LATCH_MS = 10000;
const float HEART_RATE_LOW_BPM = 45.0f;
const float HEART_RATE_HIGH_BPM = 130.0f;
const unsigned long HEART_SAMPLE_INTERVAL_MS = 2;
const unsigned long HEART_ALARM_CONFIRM_MS = 3000;
const unsigned long BUZZER_TOGGLE_MS = 250;
const unsigned long SAMPLE_INTERVAL_MS = 5;
const unsigned long PRINT_INTERVAL_MS = 1000;
const unsigned long SEND_INTERVAL_MS = 1000;
const unsigned long TEMPERATURE_INTERVAL_MS = 500;
const unsigned long LCD_UPDATE_INTERVAL_MS = 500;

Adafruit_MPU6050 mpu;
uint8_t mpuAddress = 0x68;
bool mpuReady = false;
bool mpuValid = false;
const char *mpuError = "NOT_INITIALIZED";
unsigned long lastSample = 0;
unsigned long lastPrint = 0;
unsigned long lastSend = 0;
unsigned long lastTemperatureRead = 0;
bool alarmActive = false;
float peakG = 0.0f;
float axG = 0.0f, ayG = 0.0f, azG = 0.0f, totalG = 0.0f;
enum FallPhase { FALL_MONITORING, FALL_FREE_FALL, FALL_IMPACT };
FallPhase fallPhase = FALL_MONITORING;
unsigned long lowGStarted = 0;
unsigned long fallPhaseStarted = 0;
unsigned long fallDetectedAt = 0;
bool fallDetected = false;
float fallImpactG = 0.0f;
float stableAx = 0.0f, stableAy = 0.0f, stableAz = 1.0f;
float preFallAx = 0.0f, preFallAy = 0.0f, preFallAz = 1.0f;
float ambientC = NAN, objectC = NAN;
bool mlxValid = false;
const char *mlxError = "NOT_READ";

bool lcdReady = false;
const char *lcdError = "NOT_INITIALIZED";
const char *LCD_INTERFACE = "parallel_4bit";
unsigned long lastLcdUpdate = 0;
char lcdLine1[LCD_COLUMNS + 1] = "Starting...";
char lcdLine2[LCD_COLUMNS + 1] = "Please wait";

// Published snapshots are copied from the dedicated ADC task, never shared
// while being updated. LCD/HTTP/temperature work cannot interrupt acquisition.
HeartSnapshot heartSnapshot;
QueueHandle_t heartQueue;
float heartRateBpm = NAN, lastStableHeartRateBpm = NAN;
float heartSignalAmplitude = 0;
unsigned long lastStableHeartRateAt = 0, abnormalHeartSince = 0;
unsigned long lastBuzzerToggle = 0;
int heartSignalRaw = 0;
int8_t heartPulsePolarity = 1;
uint8_t heartSignalQuality = 0;
bool heartRateValid = false, hasLastStableHeartRate = false;
bool heartRateAlarm = false, heartFingerPresent = false;
bool buzzerOn = false, remoteBuzzerRequested = false;
unsigned long lastServerResponse = 0;
char serverClassification[16] = "unavailable";
float serverConfidence = 0;
const char *heartRateError = "ACQUIRING";

SemaphoreHandle_t wireMutex;
portMUX_TYPE motionMux = portMUX_INITIALIZER_UNLOCKED;
MotionSample motionRing[MOTION_CAPACITY];
MotionSample motionSnapshot[MOTION_CAPACITY];  // Used only by the main loop.
uint16_t motionWrite = 0, motionCount = 0;
uint32_t previousMotionTime = 0;
QueueHandle_t uploadQueue, replyQueue;

String serverUrl() {
  return String(SERVER_URL);
}

// ---------- WiFi ----------
void scanTargetWiFi() {
  WiFi.mode(WIFI_STA);
  Serial.printf("Scanning for WiFi '%s'...\n", WIFI_SSID);
  int networkCount = WiFi.scanNetworks(false, true);
  bool found = false;
  for (int i = 0; i < networkCount; ++i) {
    if (WiFi.SSID(i) == WIFI_SSID) {
      found = true;
      Serial.printf("WiFi found: RSSI=%d dBm, channel=%d, encryption=%d\n",
                    WiFi.RSSI(i), WiFi.channel(i),
                    (int)WiFi.encryptionType(i));
    }
  }
  if (!found) {
    Serial.println(
        "WiFi NOT FOUND. ESP32 supports 2.4 GHz only; check hotspot band.");
  }
  WiFi.scanDelete();
}

void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Connecting to WiFi");
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 15000) {
    delay(300);
    Serial.print(".");
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("WiFi OK. IP: ");
    Serial.println(WiFi.localIP());
    Serial.print("FastAPI URL: ");
    Serial.println(serverUrl());
  } else {
    Serial.printf("WiFi FAILED, status=%d (will retry in loop)\n",
                  (int)WiFi.status());
  }
}

// ---------- MLX90614 ----------
uint8_t mlxCRC(const uint8_t *bytes, size_t count) {
  uint8_t crc = 0;
  for (size_t i = 0; i < count; ++i) {
    crc ^= bytes[i];
    for (uint8_t bit = 0; bit < 8; ++bit) {
      crc = (crc & 0x80) ? (uint8_t)((crc << 1) ^ 0x07)
                         : (uint8_t)(crc << 1);
    }
  }
  return crc;
}

bool readMLXTemperature(uint8_t reg, float &temperatureC) {
  temperatureC = NAN;
  Wire.beginTransmission(MLX_ADDRESS);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) {
    mlxError = "NO_ACK at 0x5A";
    return false;
  }
  if (Wire.requestFrom(MLX_ADDRESS, (uint8_t)3, (uint8_t)true) != 3) {
    while (Wire.available()) Wire.read();
    mlxError = "INCOMPLETE_DATA";
    return false;
  }

  uint8_t low = Wire.read();
  uint8_t high = Wire.read();
  uint8_t pec = Wire.read();
  const uint8_t message[] = {
      (uint8_t)(MLX_ADDRESS << 1), reg,
      (uint8_t)((MLX_ADDRESS << 1) | 1), low, high};
  uint16_t raw = ((uint16_t)high << 8) | low;
  if (mlxCRC(message, sizeof(message)) != pec) {
    mlxError = "CRC_ERROR";
    return false;
  }
  if ((raw & 0x8000) || raw == 0) {
    mlxError = "INVALID_TEMPERATURE";
    return false;
  }
  temperatureC = raw * 0.02f - 273.15f;
  return true;
}

void updateMLX() {
  if (xSemaphoreTake(wireMutex, pdMS_TO_TICKS(10)) != pdTRUE) {
    mlxValid = false;
    mlxError = "I2C_BUSY";
    return;
  }
  mlxError = "OK";
  bool ambientOK = readMLXTemperature(0x06, ambientC);
  bool objectOK = readMLXTemperature(0x07, objectC);
  mlxValid = ambientOK && objectOK;
  xSemaphoreGive(wireMutex);
}

// ---------- Bare 16-pin LCD1602A, 4-bit parallel mode ----------
void lcdPulseEnable() {
  digitalWrite(LCD_ENABLE_PIN, LOW);
  delayMicroseconds(1);
  digitalWrite(LCD_ENABLE_PIN, HIGH);
  delayMicroseconds(1);
  digitalWrite(LCD_ENABLE_PIN, LOW);
  delayMicroseconds(100);
}

void lcdWrite4Bits(uint8_t value) {
  digitalWrite(LCD_D4_PIN, (value >> 0) & 0x01);
  digitalWrite(LCD_D5_PIN, (value >> 1) & 0x01);
  digitalWrite(LCD_D6_PIN, (value >> 2) & 0x01);
  digitalWrite(LCD_D7_PIN, (value >> 3) & 0x01);
  lcdPulseEnable();
}

void lcdSend(uint8_t value, bool dataMode) {
  digitalWrite(LCD_RS_PIN, dataMode ? HIGH : LOW);
  lcdWrite4Bits(value >> 4);
  lcdWrite4Bits(value & 0x0F);
}

void lcdCommand(uint8_t value) {
  lcdSend(value, false);
  if (value == 0x01 || value == 0x02) delayMicroseconds(2000);
}

void lcdWriteCharacter(char value) {
  lcdSend((uint8_t)value, true);
}

void lcdSetCursor(uint8_t column, uint8_t row) {
  const uint8_t rowOffsets[] = {0x00, 0x40};
  lcdCommand(0x80 | (column + rowOffsets[row > 0 ? 1 : 0]));
}

void lcdPrintLine(uint8_t row, const char *text) {
  lcdSetCursor(0, row);
  size_t length = strlen(text);
  for (uint8_t i = 0; i < LCD_COLUMNS; ++i) {
    lcdWriteCharacter(i < length ? text[i] : ' ');
  }
}

void initLCD() {
  pinMode(LCD_RS_PIN, OUTPUT);
  pinMode(LCD_ENABLE_PIN, OUTPUT);
  pinMode(LCD_D4_PIN, OUTPUT);
  pinMode(LCD_D5_PIN, OUTPUT);
  pinMode(LCD_D6_PIN, OUTPUT);
  pinMode(LCD_D7_PIN, OUTPUT);
  digitalWrite(LCD_RS_PIN, LOW);
  digitalWrite(LCD_ENABLE_PIN, LOW);

  // HD44780 initialization sequence for power-up directly into 4-bit mode.
  delay(50);
  lcdWrite4Bits(0x03);
  delayMicroseconds(4500);
  lcdWrite4Bits(0x03);
  delayMicroseconds(4500);
  lcdWrite4Bits(0x03);
  delayMicroseconds(150);
  lcdWrite4Bits(0x02);
  lcdCommand(0x28);  // 4-bit, two lines, 5x8 font.
  lcdCommand(0x0C);  // Display on, cursor and blink off.
  lcdCommand(0x01);  // Clear display.
  lcdCommand(0x06);  // Left-to-right entry mode.

  lcdReady = true;
  lcdError = "OK";
  lcdPrintLine(0, "Elder Sensors");
  lcdPrintLine(1, "Starting...");
}

void updateLCD(unsigned long now) {
  if (!lcdReady || now - lastLcdUpdate < LCD_UPDATE_INTERVAL_MS) return;
  portENTER_CRITICAL(&motionMux);
  bool fallDetected = ::fallDetected;
  portEXIT_CRITICAL(&motionMux);
  lastLcdUpdate = now;
  char nextLine1[LCD_COLUMNS + 1] = {0};
  char nextLine2[LCD_COLUMNS + 1] = {0};

  bool serverAlertCurrent = remoteBuzzerRequested &&
                            now - lastServerResponse < SEND_INTERVAL_MS * 3;
  bool serverCritical = serverAlertCurrent &&
                        strcmp(serverClassification, "critical") == 0;
  if (fallDetected || serverAlertCurrent) {
    snprintf(nextLine1, sizeof(nextLine1),
             (fallDetected || serverCritical) ? "CRITICAL ALERT"
                                              : "WARNING ALERT");
    snprintf(nextLine2, sizeof(nextLine2),
             fallDetected ? "FALL DETECTED" : "CHECK PATIENT");
  } else if (heartRateValid) {
    if (heartRateAlarm) {
      snprintf(nextLine1, sizeof(nextLine1), "HR:%3.0f ALARM", heartRateBpm);
    } else {
      snprintf(nextLine1, sizeof(nextLine1), "HR:%3.0f BPM", heartRateBpm);
    }
  } else if (hasLastStableHeartRate) {
    snprintf(nextLine1, sizeof(nextLine1), "HR:%3.0f BPM",
             lastStableHeartRateBpm);
  } else {
    snprintf(nextLine1, sizeof(nextLine1),
      !heartFingerPresent ? "HR: PLACE FINGER" : "HR: DETECTING");
  }

  if (!fallDetected && !serverAlertCurrent) {
    if (mlxValid) {
      snprintf(nextLine2, sizeof(nextLine2), "Body:%4.1f C", objectC);
    } else {
      snprintf(nextLine2, sizeof(nextLine2), "Body: --.- C");
    }
  }

  if (strcmp(nextLine1, lcdLine1) != 0) {
    snprintf(lcdLine1, sizeof(lcdLine1), "%s", nextLine1);
    lcdPrintLine(0, lcdLine1);
  }
  if (strcmp(nextLine2, lcdLine2) != 0) {
    snprintf(lcdLine2, sizeof(lcdLine2), "%s", nextLine2);
    lcdPrintLine(1, lcdLine2);
  }
}

// ---------- MPU6050 ----------
bool readMPUMotion(MotionSample &sample, const char *&error) {
  Wire.beginTransmission(mpuAddress);
  Wire.write((uint8_t)0x3B);
  if (Wire.endTransmission(false) != 0) {
    error = "NO_ACK";
    return false;
  }
  // Burst read: acceleration XYZ, temperature, angular velocity XYZ.
  if (Wire.requestFrom(mpuAddress, (uint8_t)14, (uint8_t)true) != 14) {
    while (Wire.available()) Wire.read();
    error = "INCOMPLETE_DATA";
    return false;
  }
  int16_t raw[7];
  for (int i = 0; i < 7; ++i) {
    uint8_t high = Wire.read(), low = Wire.read();
    raw[i] = (int16_t)(((uint16_t)high << 8) | low);
  }
  sample.timestampMs = millis();
  for (int i = 0; i < 3; ++i) {
    sample.values[i] = raw[i] / 2048.0f;       // MPU6050 +/-16 g.
    sample.values[i + 3] = raw[i + 4] / 16.4f; // MPU6050 +/-2000 deg/s.
  }
  error = "OK";
  return true;
}

const char *fallStateName() {
  if (fallDetected) return "FALL_CONFIRMED";
  if (fallPhase == FALL_FREE_FALL) return "FREE_FALL";
  if (fallPhase == FALL_IMPACT) return "IMPACT_CHECK";
  return "MONITORING";
}

void resetFallCandidate() {
  fallPhase = FALL_MONITORING;
  lowGStarted = 0;
  fallPhaseStarted = 0;
}

float postureAngleDegrees(float ax1, float ay1, float az1,
                          float ax2, float ay2, float az2) {
  float firstMagnitude = sqrtf(ax1 * ax1 + ay1 * ay1 + az1 * az1);
  float secondMagnitude = sqrtf(ax2 * ax2 + ay2 * ay2 + az2 * az2);
  if (firstMagnitude < 0.1f || secondMagnitude < 0.1f) return 0.0f;
  float cosine = (ax1 * ax2 + ay1 * ay2 + az1 * az2) /
                 (firstMagnitude * secondMagnitude);
  cosine = fmaxf(-1.0f, fminf(1.0f, cosine));
  return acosf(cosine) * 180.0f / PI;
}

void updateFallDetector(unsigned long now) {
  if (!mpuValid) return;

  if (fallDetected) {
    alarmActive = true;
    if (now - fallDetectedAt >= FALL_LATCH_MS) {
      fallDetected = false;
      alarmActive = false;
      resetFallCandidate();
    }
    return;
  }

  if (fallPhase == FALL_MONITORING) {
    if (totalG >= STILL_MIN_G && totalG <= STILL_MAX_G) {
      stableAx = axG;
      stableAy = ayG;
      stableAz = azG;
    }
    if (totalG < FREE_FALL_THRESHOLD_G) {
      if (lowGStarted == 0) {
        lowGStarted = now;
        preFallAx = stableAx;
        preFallAy = stableAy;
        preFallAz = stableAz;
      } else if (now - lowGStarted >= FREE_FALL_CONFIRM_MS) {
        fallPhase = FALL_FREE_FALL;
        fallPhaseStarted = now;
      }
    } else {
      lowGStarted = 0;
    }
    return;
  }

  if (fallPhase == FALL_FREE_FALL) {
    if (totalG >= IMPACT_THRESHOLD_G) {
      fallPhase = FALL_IMPACT;
      fallPhaseStarted = now;
      fallImpactG = totalG;
    } else if (now - fallPhaseStarted > IMPACT_WINDOW_MS) {
      resetFallCandidate();
    }
    return;
  }

  if (fallPhase == FALL_IMPACT) {
    if (totalG > fallImpactG) fallImpactG = totalG;
    unsigned long elapsed = now - fallPhaseStarted;
    if (elapsed >= POST_IMPACT_SETTLE_MS &&
        totalG >= STILL_MIN_G && totalG <= STILL_MAX_G) {
      float angle = postureAngleDegrees(
          preFallAx, preFallAy, preFallAz, axG, ayG, azG);
      if (angle >= POSTURE_CHANGE_DEGREES ||
          fallImpactG >= STRONG_IMPACT_THRESHOLD_G) {
        fallDetected = true;
        alarmActive = true;
        fallDetectedAt = now;
        return;
      }
    }
    if (elapsed > POST_IMPACT_TIMEOUT_MS) resetFallCandidate();
  }
}

// ---------- Analog heart-rate sensor + buzzer ----------
void heartTask(void *) {
  HeartRateProcessor processor;
  TickType_t wake = xTaskGetTickCount();
  const TickType_t period = pdMS_TO_TICKS(HEART_SAMPLE_INTERVAL_MS);
  unsigned long publishedAt = 0;
  for (;;) {
    unsigned long now = millis();
    processor.sample(analogRead(HEART_RATE_PIN), now);
    if (now - publishedAt >= 20) {
      HeartSnapshot snapshot = processor.snapshot(now);
      xQueueOverwrite(heartQueue, &snapshot);
      publishedAt = now;
    }
    if (xTaskGetTickCount() - wake >= period) wake = xTaskGetTickCount();
    vTaskDelayUntil(&wake, period);
  }
}

void updateHeartRate(unsigned long now) {
  if (xQueueReceive(heartQueue, &heartSnapshot, 0) != pdTRUE) return;
  heartRateBpm = heartSnapshot.bpm;
  heartRateValid = heartSnapshot.valid;
  lastStableHeartRateBpm = heartSnapshot.displayBpm;
  hasLastStableHeartRate = isfinite(lastStableHeartRateBpm);
  lastStableHeartRateAt = heartSnapshot.lastValidAt;
  heartSignalRaw = heartSnapshot.raw;
  heartSignalAmplitude = heartSnapshot.amplitude;
  heartSignalQuality = heartSnapshot.quality;
  heartFingerPresent = heartSnapshot.contact;
  heartRateError = heartSnapshot.state;
  bool abnormal = heartRateValid &&
      (heartRateBpm < HEART_RATE_LOW_BPM || heartRateBpm > HEART_RATE_HIGH_BPM);
  if (abnormal) {
    if (!abnormalHeartSince) abnormalHeartSince = now;
    heartRateAlarm = now - abnormalHeartSince >= HEART_ALARM_CONFIRM_MS;
  } else { abnormalHeartSince = 0; heartRateAlarm = false; }
}

void updateBuzzer(unsigned long now) {
  bool serverRequestCurrent = remoteBuzzerRequested &&
                              now - lastServerResponse < SEND_INTERVAL_MS * 3;
  // The buzzer has exactly one authority: the backend model classification.
  // Local signal noise, raw thresholds and fall candidates never sound it.
  if (!serverRequestCurrent) {
    buzzerOn = false;
    digitalWrite(BUZZER_PIN, LOW);
    return;
  }

  if (now - lastBuzzerToggle >= BUZZER_TOGGLE_MS) {
    lastBuzzerToggle = now;
    buzzerOn = !buzzerOn;
    digitalWrite(BUZZER_PIN, buzzerOn ? HIGH : LOW);
  }
}

// Sampling has its own task; HTTP, serial output and LCD updates cannot
// deliberately pause the motion stream. Actual timestamps expose timing gaps.
void motionTask(void *) {
  TickType_t wake = xTaskGetTickCount();
  const TickType_t period = pdMS_TO_TICKS(SAMPLE_INTERVAL_MS);
  for (;;) {
    MotionSample sample;
    const char *error = "I2C_BUSY";
    bool valid = false;
    if (xSemaphoreTake(wireMutex, pdMS_TO_TICKS(2)) == pdTRUE) {
      valid = readMPUMotion(sample, error);
      xSemaphoreGive(wireMutex);
    }
    portENTER_CRITICAL(&motionMux);
    mpuValid = valid;
    mpuError = error;
    if (valid) {
      uint32_t now = sample.timestampMs;
      if (now <= previousMotionTime || now - previousMotionTime > 15) {
        motionCount = 0;
        resetFallCandidate();
      }
      previousMotionTime = now;
      axG = sample.values[0]; ayG = sample.values[1]; azG = sample.values[2];
      totalG = sqrtf(axG * axG + ayG * ayG + azG * azG);
      if (totalG > peakG) peakG = totalG;
      updateFallDetector(now);
      motionRing[motionWrite] = sample;
      motionWrite = (motionWrite + 1) % MOTION_CAPACITY;
      if (motionCount < MOTION_CAPACITY) ++motionCount;
    } else {
      motionCount = 0;
      resetFallCandidate();
    }
    portEXIT_CRITICAL(&motionMux);
    if (xTaskGetTickCount() - wake >= period) wake = xTaskGetTickCount();
    vTaskDelayUntil(&wake, period);
  }
}

// ---------- JSON ----------
void setJSONReading(JsonDocument &data, const char *key, float value,
                    bool valid) {
  if (valid && isfinite(value)) {
    data[key] = roundf(value * 100.0f) / 100.0f;
  } else {
    data[key] = nullptr;
  }
}

String buildJSON() {
  // Copy under a short lock, then serialize without blocking the sampler.
  portENTER_CRITICAL(&motionMux);
  uint16_t sampleCount = motionCount;
  for (uint16_t i = 0; i < sampleCount; ++i) {
    motionSnapshot[i] = motionRing[(motionWrite + MOTION_CAPACITY - sampleCount + i) % MOTION_CAPACITY];
  }
  bool mpuValid = ::mpuValid, fallDetected = ::fallDetected, alarmActive = ::alarmActive;
  float axG = ::axG, ayG = ::ayG, azG = ::azG, totalG = ::totalG;
  float peakG = ::peakG, fallImpactG = ::fallImpactG;
  const char *mpuError = ::mpuError, *fallState = fallStateName();
  ::peakG = 0.0f;
  portEXIT_CRITICAL(&motionMux);

  JsonDocument data;
  data["device_id"] = DEVICE_ID;
  data["patient_id"] = PATIENT_ID;
  data["uptime_ms"] = millis();
  setJSONReading(data, "accel_x_g", axG, mpuValid);
  setJSONReading(data, "accel_y_g", ayG, mpuValid);
  setJSONReading(data, "accel_z_g", azG, mpuValid);
  setJSONReading(data, "accel_total_g", totalG, mpuValid);
  setJSONReading(data, "accel_peak_g", peakG, mpuValid);
  setJSONReading(data, "ambient_temp_c", ambientC, mlxValid);
  setJSONReading(data, "object_temp_c", objectC, mlxValid);
  data["mpu6050_ok"] = mpuValid;
  data["mlx90614_ok"] = mlxValid;
  data["mpu6050_error"] = mpuValid ? (const char *)nullptr : mpuError;
  data["mlx90614_error"] = mlxValid ? (const char *)nullptr : mlxError;
  data["alarm"] = mpuValid ? alarmActive : false;
  data["fall_detected"] = mpuValid ? fallDetected : false;
  data["fall_state"] = mpuValid ? fallState : "SENSOR_ERROR";
  setJSONReading(data, "fall_impact_g", fallImpactG, mpuValid);
  if (!mpuValid) {
    data["alarm"] = nullptr;
    data["fall_detected"] = nullptr;
  }
  setJSONReading(data, "heart_rate_bpm", heartRateBpm, heartRateValid);
  setJSONReading(data, "heart_rate_display_bpm", lastStableHeartRateBpm,
                 hasLastStableHeartRate);
  data["heart_rate_held"] = hasLastStableHeartRate && !heartRateValid;
  if (hasLastStableHeartRate) {
    data["heart_rate_last_valid_age_ms"] = millis() - lastStableHeartRateAt;
  } else {
    data["heart_rate_last_valid_age_ms"] = nullptr;
  }
  data["heart_sample_count"] = heartSnapshot.sampleCount;
  data["heart_sampling_gap_count"] = heartSnapshot.gapCount;
  data["heart_sample_rate_hz"] = 500;
  data["heart_rate_signal_state"] = heartSnapshot.state;
  data["heart_filtered_signal"] = heartSnapshot.filtered;
  data["heart_rate_beat_at_ms"] = heartSnapshot.lastValidAt;
  data["heart_signal_raw"] = heartSignalRaw;
  data["heart_signal_amplitude"] = roundf(heartSignalAmplitude * 10.0f) / 10.0f;
  data["heart_signal_quality"] = heartSignalQuality;
  data["heart_pulse_polarity"] = heartPulsePolarity > 0 ? "positive" : "negative";
  data["heart_finger_detected"] = heartFingerPresent;
  data["heart_rate_ok"] = heartRateValid;
  data["heart_rate_error"] =
      heartRateValid ? (const char *)nullptr : heartRateError;
  data["heart_rate_alarm"] = heartRateValid ? heartRateAlarm : false;
  data["buzzer_ok"] = true;
  data["buzzer_error"] = nullptr;
  data["buzzer_on"] = buzzerOn;
  data["last_server_classification"] = serverClassification;
  data["last_server_confidence"] = serverConfidence;
  data["lcd_ok"] = lcdReady;
  data["lcd_error"] = lcdReady ? (const char *)nullptr : lcdError;
  data["lcd_interface"] = LCD_INTERFACE;
  data["lcd_line_1"] = lcdLine1;
  data["lcd_line_2"] = lcdLine2;

  if (mpuValid && sampleCount == MOTION_CAPACITY) {
    JsonObject window = data["motion_window"].to<JsonObject>();
    window["sample_rate_hz"] = 200;
    JsonArray channels = window["channels"].to<JsonArray>();
    const char *names[] = {"accel_x_g", "accel_y_g", "accel_z_g", "gyro_x_dps", "gyro_y_dps", "gyro_z_dps"};
    for (const char *name : names) channels.add(name);
    window["units"]["acceleration"] = "g";
    window["units"]["angular_velocity"] = "deg/s";
    JsonArray samples = window["samples"].to<JsonArray>();
    JsonArray times = window["timestamps_ms"].to<JsonArray>();
    for (uint16_t i = 0; i < sampleCount; ++i) {
      times.add(motionSnapshot[i].timestampMs);
      JsonArray row = samples.add<JsonArray>();
      for (uint8_t channel = 0; channel < 6; ++channel) {
        row.add(roundf(motionSnapshot[i].values[channel] * 10000.0f) / 10000.0f);
      }
    }
  }

  String out;
  serializeJson(data, out);
  return out;
}

// ---------- HTTP POST ----------
void networkTask(void *) {
  for (;;) {
    if (WiFi.status() != WL_CONNECTED) connectWiFi();
    UploadJob job;
    if (xQueueReceive(uploadQueue, &job, pdMS_TO_TICKS(500)) != pdTRUE) continue;
    ServerReply reply = {};
    reply.requestCreatedAt = job.createdAt;
    if (WiFi.status() == WL_CONNECTED && millis() - job.createdAt < 1000) {
      WiFiClient client;
      HTTPClient http;
      http.setTimeout(HTTP_TIMEOUT_MS);
      if (serverUrl().startsWith("http://") && http.begin(client, serverUrl())) {
        http.addHeader("Content-Type", "application/json");
        int code = http.POST((uint8_t *)job.json, strlen(job.json));
        if (code >= 200 && code < 300) {
          JsonDocument response;
          if (!deserializeJson(response, http.getString())) {
            const char *level = response["classification"] | "unavailable";
            snprintf(reply.classification, sizeof(reply.classification), "%s", level);
            reply.confidence = response["confidence"] | 0.0f;
            reply.ok = true;
          }
        }
        http.end();
      }
    }
    free(job.json);
    xQueueOverwrite(replyQueue, &reply);
  }
}

// ---------- Setup ----------
void setup() {
  Serial.begin(115200);
  delay(1000);

  analogReadResolution(12);
  pinMode(HEART_RATE_PIN, INPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);
  heartQueue = xQueueCreate(1, sizeof(HeartSnapshot));
  configASSERT(heartQueue);
  BaseType_t heartCreated = xTaskCreate(heartTask, "heart500Hz", 4096, nullptr, 4, nullptr);
  configASSERT(heartCreated == pdPASS);
  initLCD();

  scanTargetWiFi();
  connectWiFi();

  wireMutex = xSemaphoreCreateMutex();
  uploadQueue = xQueueCreate(1, sizeof(UploadJob));
  replyQueue = xQueueCreate(1, sizeof(ServerReply));
  configASSERT(wireMutex && uploadQueue && replyQueue);
  Wire.begin(MPU_SDA, MPU_SCL);
  Wire.setClock(100000);
  Wire.setTimeOut(10);

  mpuReady = mpu.begin(0x68, &Wire);
  if (!mpuReady) {
    mpuAddress = 0x69;
    mpuReady = mpu.begin(mpuAddress, &Wire);
  }

  if (mpuReady) {
    mpu.setAccelerometerRange(MPU6050_RANGE_16_G);
    mpu.setGyroRange(MPU6050_RANGE_2000_DEG);
    mpu.setFilterBandwidth(MPU6050_BAND_44_HZ);
    mpu.setSampleRateDivisor(4);
    BaseType_t motionCreated = xTaskCreate(motionTask, "motion200Hz", 4096, nullptr, 3, nullptr);
    configASSERT(motionCreated == pdPASS);
  } else {
    mpuError = "NOT_FOUND: check SDA=21, SCL=22 and power";
  }

  updateMLX();
  lastTemperatureRead = millis();
  lastLcdUpdate = millis() - LCD_UPDATE_INTERVAL_MS;
  updateLCD(millis());
  BaseType_t networkCreated = xTaskCreate(networkTask, "sensorUpload", 16384, nullptr, 1, nullptr);
  configASSERT(networkCreated == pdPASS);
}

// ---------- Loop ----------
void loop() {
  unsigned long now = millis();

  updateHeartRate(now);

  ServerReply reply;
  if (xQueueReceive(replyQueue, &reply, 0) == pdTRUE) {
    if (reply.ok && now - reply.requestCreatedAt < SEND_INTERVAL_MS * 3) {
      snprintf(serverClassification, sizeof(serverClassification), "%s", reply.classification);
      serverConfidence = reply.confidence;
      remoteBuzzerRequested = strcmp(serverClassification, "warning") == 0 ||
                              strcmp(serverClassification, "critical") == 0;
      lastServerResponse = reply.requestCreatedAt;
    } else {
      remoteBuzzerRequested = false;
    }
  }

  if (now - lastTemperatureRead >= TEMPERATURE_INTERVAL_MS) {
    lastTemperatureRead = now;
    updateMLX();
  }

  updateBuzzer(now);
  updateLCD(now);

  if (now - lastPrint >= PRINT_INTERVAL_MS) {
    lastPrint = now;
    Serial.printf("Server: %s | score %.3f\n", serverClassification, serverConfidence);
  }

  if (now - lastSend >= SEND_INTERVAL_MS) {
    lastSend = now;
    if (uxQueueSpacesAvailable(uploadQueue) > 0) {
      String json = buildJSON();
      UploadJob job = {strdup(json.c_str()), millis()};
      if (job.json && xQueueSend(uploadQueue, &job, 0) != pdTRUE) free(job.json);
    }
  }

  delay(1);
}
