#include <Wire.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <ArduinoJson.h>
#include <math.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <time.h>
#include <esp_sntp.h>
#include <esp_random.h>
#include <mbedtls/md.h>
#include <mbedtls/sha256.h>
#include <HTTPClient.h>

#include "secrets.h"
#include "gateway_ca.h"
#include "device_auth.h"
#include "device_signing.h"
#include "upload_diagnostics.h"
#include <mbedtls/x509.h>

// Keep library-level HTTP diagnostics from ever dumping authentication headers.
#if defined(CORE_DEBUG_LEVEL) && CORE_DEBUG_LEVEL != 0
#error "CareLink device authentication requires Tools > Core Debug Level > None"
#endif

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
const char *DEVICE_ID = DEVICE_AUTH_ID;
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
const unsigned long HEART_AVERAGE_WINDOW_MS = 20;
const uint8_t HEART_MOVING_AVERAGE_SIZE = 4;
const uint8_t HEART_RISE_THRESHOLD = 4;
// Calibrated from this connected module. A short confirmation time allows a
// light finger touch (observed near 2090) while rejecting isolated ADC spikes.
const int HEART_FINGER_ON_RAW = 1950;
const int HEART_FINGER_OFF_RAW = 1850;
const unsigned long HEART_CONTACT_CONFIRM_MS = 250;
const unsigned long HEART_CONTACT_SETTLE_MS = 600;
const unsigned long HEART_MIN_BEAT_INTERVAL_MS = 300;   // 200 BPM maximum.
const unsigned long HEART_MAX_BEAT_INTERVAL_MS = 2000;  // 30 BPM minimum.
const unsigned long HEART_NO_BEAT_TIMEOUT_MS = 3000;
const unsigned long HEART_ALARM_CONFIRM_MS = 3000;
const float HEART_MIN_SIGNAL_AMPLITUDE = 4.0f;
const float HEART_INTERVAL_TOLERANCE = 0.30f;
const uint8_t HEART_REQUIRED_INTERVALS = 1;
const unsigned long BUZZER_TOGGLE_MS = 250;
const unsigned long SAMPLE_INTERVAL_MS = 10;
const unsigned long PRINT_INTERVAL_MS = 200;
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

// Analog heart-rate state. The adaptive baseline supports common S/V/G pulse
// sensor modules without adding another Arduino library.
unsigned long lastHeartSample = 0;
unsigned long heartAverageWindowStarted = 0;
unsigned long lastBeat = 0;
unsigned long heartContactStarted = 0;
unsigned long heartContactCandidateStarted = 0;
unsigned long abnormalHeartSince = 0;
unsigned long lastBuzzerToggle = 0;
uint32_t heartSampleSum = 0;
uint16_t heartSampleCount = 0;
int heartSignalRaw = 0;
float heartFiltered = 0.0f;
float heartBaseline = 0.0f;
float heartEnvelope = 0.0f;
float heartPositiveEnvelope = 0.0f;
float heartNegativeEnvelope = 0.0f;
float heartSignalAmplitude = 0.0f;
float heartRateBpm = NAN;
float lastStableHeartRateBpm = NAN;
unsigned long lastStableHeartRateAt = 0;
bool heartInitialized = false;
bool heartRateValid = false;
bool hasLastStableHeartRate = false;
bool heartRateAlarm = false;
bool heartPulseArmed = true;
bool heartFingerPresent = false;
int8_t heartPulsePolarity = 1;
uint8_t heartSignalQuality = 0;
float heartMovingReadings[HEART_MOVING_AVERAGE_SIZE] = {0};
float heartMovingSum = 0.0f;
float previousDirectionalPulse = 0.0f;
uint8_t heartMovingIndex = 0;
uint8_t heartMovingCount = 0;
uint8_t heartRiseCount = 0;
bool heartCurveRising = false;
bool buzzerOn = false;
bool remoteBuzzerRequested = false;
unsigned long lastServerResponse = 0;
char serverClassification[16] = "unavailable";
float serverConfidence = 0.0f;
const char *heartRateError = "WAITING_FOR_PULSE";
const uint8_t HEART_INTERVAL_COUNT = 5;
unsigned long heartIntervals[HEART_INTERVAL_COUNT] = {0};
uint8_t heartIntervalIndex = 0;
uint8_t heartIntervalsValid = 0;

String serverUrl() {
  return String(SERVER_URL);
}

// ---------- Device authentication / clock ----------
volatile bool authClockSynchronized = false;
volatile unsigned long authClockLastSync = 0;
bool authClockReported = false;
unsigned long authRetryAt = 0;
uint32_t authRetryDelayMs = 1000;

void authTimeAvailable(struct timeval *) {
  authClockLastSync = millis();
  authClockSynchronized = true;
}

void scheduleAuthRetry() {
  authRetryDelayMs = authRetryDelayMs < 30000 ? authRetryDelayMs * 2 : 30000;
  if (authRetryDelayMs > 30000) authRetryDelayMs = 30000;
  authRetryAt = millis() + authRetryDelayMs;
}

int authSHA256(const uint8_t *body, size_t size, uint8_t *digest) {
  return mbedtls_sha256(body, size, digest, 0);
}

int authHMAC256(const uint8_t *key, size_t keySize, const uint8_t *body, size_t size, uint8_t *digest) {
  const mbedtls_md_info_t *info = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
  return info ? mbedtls_md_hmac(info, key, keySize, body, size, digest) : -1;
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
    Serial.println("[CareLink] WiFi connected");
    // SNTP is asynchronous. If time cannot be established, HTTPS fails closed.
    authClockSynchronized = false;
    authClockReported = false;
    esp_sntp_set_time_sync_notification_cb(authTimeAvailable);
    configTime(0, 0, "time.apple.com", "pool.ntp.org", "time.cloudflare.com");
    Serial.println("[CareLink] SNTP synchronization requested");
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
  mlxError = "OK";
  bool ambientOK = readMLXTemperature(0x06, ambientC);
  bool objectOK = readMLXTemperature(0x07, objectC);
  mlxValid = ambientOK && objectOK;
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
bool readMPUAcceleration() {
  Wire.beginTransmission(mpuAddress);
  Wire.write((uint8_t)0x3B);
  if (Wire.endTransmission(false) != 0) {
    mpuError = "NO_ACK";
    return false;
  }
  if (Wire.requestFrom(mpuAddress, (uint8_t)6, (uint8_t)true) != 6) {
    while (Wire.available()) Wire.read();
    mpuError = "INCOMPLETE_DATA";
    return false;
  }
  int16_t raw[3];
  for (int i = 0; i < 3; ++i) {
    uint8_t high = Wire.read();
    uint8_t low = Wire.read();
    raw[i] = (int16_t)(((uint16_t)high << 8) | low);
  }
  axG = raw[0] / 4096.0f;
  ayG = raw[1] / 4096.0f;
  azG = raw[2] / 4096.0f;
  totalG = sqrtf(axG * axG + ayG * ayG + azG * azG);
  mpuError = "OK";
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
void clearHeartIntervals() {
  for (uint8_t i = 0; i < HEART_INTERVAL_COUNT; ++i) {
    heartIntervals[i] = 0;
  }
  heartIntervalIndex = 0;
  heartIntervalsValid = 0;
}

void resetHeartWaveform() {
  lastBeat = 0;
  heartRateBpm = NAN;
  heartRateValid = false;
  heartRateAlarm = false;
  abnormalHeartSince = 0;
  heartFiltered = 0.0f;
  heartBaseline = 0.0f;
  heartEnvelope = 0.0f;
  heartPositiveEnvelope = 0.0f;
  heartNegativeEnvelope = 0.0f;
  heartSignalAmplitude = 0.0f;
  heartSignalQuality = 0;
  heartInitialized = false;
  heartPulsePolarity = 1;
  previousDirectionalPulse = 0.0f;
  heartMovingSum = 0.0f;
  heartMovingIndex = 0;
  heartMovingCount = 0;
  heartRiseCount = 0;
  heartCurveRising = false;
  for (uint8_t i = 0; i < HEART_MOVING_AVERAGE_SIZE; ++i) {
    heartMovingReadings[i] = 0.0f;
  }
  clearHeartIntervals();
}

float medianHeartInterval() {
  if (heartIntervalsValid == 0) return 0.0f;
  unsigned long sorted[HEART_INTERVAL_COUNT];
  for (uint8_t i = 0; i < heartIntervalsValid; ++i) {
    sorted[i] = heartIntervals[i];
  }
  for (uint8_t i = 1; i < heartIntervalsValid; ++i) {
    unsigned long value = sorted[i];
    int8_t j = i - 1;
    while (j >= 0 && sorted[j] > value) {
      sorted[j + 1] = sorted[j];
      --j;
    }
    sorted[j + 1] = value;
  }
  uint8_t middle = heartIntervalsValid / 2;
  if (heartIntervalsValid % 2 == 1) return sorted[middle];
  return (sorted[middle - 1] + sorted[middle]) * 0.5f;
}

bool heartIntervalIsConsistent(unsigned long intervalMs) {
  if (heartIntervalsValid == 0) return true;
  float reference = medianHeartInterval();
  float allowedDifference = fmaxf(100.0f, reference * HEART_INTERVAL_TOLERANCE);
  return fabsf((float)intervalMs - reference) <= allowedDifference;
}

void addHeartInterval(unsigned long intervalMs) {
  heartIntervals[heartIntervalIndex] = intervalMs;
  heartIntervalIndex = (heartIntervalIndex + 1) % HEART_INTERVAL_COUNT;
  if (heartIntervalsValid < HEART_INTERVAL_COUNT) ++heartIntervalsValid;

  // The median rejects an occasional motion spike better than a plain average.
  float stableInterval = medianHeartInterval();
  heartRateBpm = 60000.0f / stableInterval;
  // After contact settling, two detected peaks provide the first BPM. Later
  // intervals continuously replace it with the rolling median.
  heartRateValid = heartIntervalsValid >= HEART_REQUIRED_INTERVALS;
  if (heartRateValid) {
    lastStableHeartRateBpm = heartRateBpm;
    lastStableHeartRateAt = millis();
    hasLastStableHeartRate = true;
  }
  heartRateError = heartRateValid ? "OK" : "STABILIZING";
}

void updateHeartRate(unsigned long now) {
  if (now - lastHeartSample < HEART_SAMPLE_INTERVAL_MS) return;
  lastHeartSample = now;

  // KY-039 reference processing: average every ADC sample collected during a
  // 20 ms block. This rejects much of the 50 Hz interference from room lights.
  int instantRaw = analogRead(HEART_RATE_PIN);
  heartSignalRaw = instantRaw;
  heartSampleSum += instantRaw;
  ++heartSampleCount;
  if (heartAverageWindowStarted == 0) heartAverageWindowStarted = now;
  if (now - heartAverageWindowStarted < HEART_AVERAGE_WINDOW_MS) return;

  float reader = heartSampleCount > 0
                     ? (float)heartSampleSum / heartSampleCount
                     : (float)instantRaw;
  heartSignalRaw = (int)lroundf(reader);
  heartSampleSum = 0;
  heartSampleCount = 0;
  heartAverageWindowStarted = now;

  if (heartSignalRaw <= 5 || heartSignalRaw >= 4090) {
    heartFingerPresent = false;
    resetHeartWaveform();
    heartRateError = "ADC_SATURATED: check S/V/G wiring";
    return;
  }

  // Hysteresis prevents ordinary pulse variation from repeatedly changing the
  // contact state. These thresholds match the observed connected module.
  if (!heartFingerPresent && heartSignalRaw >= HEART_FINGER_ON_RAW) {
    if (heartContactCandidateStarted == 0) {
      heartContactCandidateStarted = now;
    } else if (now - heartContactCandidateStarted >= HEART_CONTACT_CONFIRM_MS) {
      heartFingerPresent = true;
      heartContactStarted = now;
      heartContactCandidateStarted = 0;
      hasLastStableHeartRate = false;
      lastStableHeartRateBpm = NAN;
      lastStableHeartRateAt = 0;
      resetHeartWaveform();
      heartRateError = "FINGER_DETECTED: hold still";
    }
  } else if (!heartFingerPresent) {
    heartContactCandidateStarted = 0;
  } else if (heartFingerPresent && heartSignalRaw <= HEART_FINGER_OFF_RAW) {
    heartFingerPresent = false;
    heartContactStarted = 0;
    heartContactCandidateStarted = 0;
    hasLastStableHeartRate = false;
    lastStableHeartRateBpm = NAN;
    lastStableHeartRateAt = 0;
    resetHeartWaveform();
    heartRateError = "NO_FINGER: cover the optical sensor";
  }

  if (!heartFingerPresent) {
    heartRateError = "NO_FINGER: cover the optical sensor";
    return;
  }
  if (now - heartContactStarted < HEART_CONTACT_SETTLE_MS) {
    heartRateError = "FINGER_DETECTED: hold still";
    return;
  }

  // The reference method then uses a four-reading moving average, giving an
  // 80 ms smoothed optical waveform without blocking the rest of the device.
  heartMovingSum -= heartMovingReadings[heartMovingIndex];
  heartMovingReadings[heartMovingIndex] = reader;
  heartMovingSum += reader;
  heartMovingIndex = (heartMovingIndex + 1) % HEART_MOVING_AVERAGE_SIZE;
  if (heartMovingCount < HEART_MOVING_AVERAGE_SIZE) ++heartMovingCount;
  heartFiltered = heartMovingSum / heartMovingCount;
  if (!heartInitialized || heartMovingCount < HEART_MOVING_AVERAGE_SIZE) {
    heartBaseline = heartFiltered;
    heartInitialized = true;
    heartRateError = "STABILIZING: filtering optical signal";
    return;
  }

  // Remove the large constant optical level, leaving the small pulse wave.
  heartBaseline = heartBaseline * 0.98f + heartFiltered * 0.02f;
  float pulseSignal = heartFiltered - heartBaseline;
  heartPositiveEnvelope =
      fmaxf(fmaxf(pulseSignal, 0.0f), heartPositiveEnvelope * 0.98f);
  heartNegativeEnvelope =
      fmaxf(fmaxf(-pulseSignal, 0.0f), heartNegativeEnvelope * 0.98f);
  heartEnvelope = fmaxf(heartPositiveEnvelope, heartNegativeEnvelope);

  // Some S/V/G pulse modules produce upward peaks, while others produce
  // downward peaks. Select the stronger side automatically.
  float selectedEnvelope = heartPulsePolarity > 0
                               ? heartPositiveEnvelope
                               : heartNegativeEnvelope;
  float oppositeEnvelope = heartPulsePolarity > 0
                               ? heartNegativeEnvelope
                               : heartPositiveEnvelope;
  if (!heartRateValid && oppositeEnvelope > selectedEnvelope * 1.25f) {
    heartPulsePolarity = -heartPulsePolarity;
    selectedEnvelope = oppositeEnvelope;
  }
  heartSignalAmplitude = selectedEnvelope;
  float quality = (heartSignalAmplitude - HEART_MIN_SIGNAL_AMPLITUDE) *
                  2.5f + heartIntervalsValid * 15.0f;
  heartSignalQuality = (uint8_t)constrain((int)lroundf(quality), 0, 100);

  float directionalPulse = heartPulsePolarity > 0 ? pulseSignal : -pulseSignal;
  float triggerLevel =
      fmaxf(HEART_MIN_SIGNAL_AMPLITUDE, selectedEnvelope * 0.45f);

  // Official-style curve detector: more than four consecutive rising 20 ms
  // readings indicate the start of one heartbeat. The amplitude requirement
  // prevents a slow finger-placement change from being counted as a beat.
  if (directionalPulse > previousDirectionalPulse) {
    if (heartRiseCount < 255) ++heartRiseCount;
  } else {
    heartCurveRising = false;
    heartRiseCount = 0;
  }
  bool pulsePeak = !heartCurveRising &&
                   heartRiseCount > HEART_RISE_THRESHOLD &&
                   directionalPulse >= triggerLevel &&
                   selectedEnvelope >= HEART_MIN_SIGNAL_AMPLITUDE;
  if (pulsePeak) heartCurveRising = true;
  previousDirectionalPulse = directionalPulse;

  if (pulsePeak && now - lastBeat >= HEART_MIN_BEAT_INTERVAL_MS) {
    unsigned long intervalMs = lastBeat == 0 ? 0 : now - lastBeat;
    if (lastBeat == 0) {
      lastBeat = now;
      heartRateError = "STABILIZING: first pulse detected";
    } else if (intervalMs >= HEART_MIN_BEAT_INTERVAL_MS &&
               intervalMs <= HEART_MAX_BEAT_INTERVAL_MS) {
      if (heartIntervalIsConsistent(intervalMs)) {
        lastBeat = now;
        addHeartInterval(intervalMs);
      } else {
        float reference = medianHeartInterval();
        // Recover cleanly if exactly one beat was missed.
        if (reference > 0.0f && intervalMs > reference * 1.70f &&
            intervalMs < reference * 2.30f &&
            heartIntervalIsConsistent(intervalMs / 2)) {
          lastBeat = now;
          addHeartInterval(intervalMs / 2);
        }
        // An early inconsistent peak is treated as movement/noise and ignored.
        heartRateError = "STABILIZING: rejecting motion noise";
      }
    } else if (intervalMs > HEART_MAX_BEAT_INTERVAL_MS) {
      lastBeat = now;
      heartRateValid = false;
      heartRateBpm = NAN;
      heartRateError = "STABILIZING: pulse sequence restarted";
      clearHeartIntervals();
    }
  }

  if (lastBeat == 0 || now - lastBeat > HEART_NO_BEAT_TIMEOUT_MS) {
    heartRateValid = false;
    heartRateBpm = NAN;
    heartRateError = heartSignalAmplitude < HEART_MIN_SIGNAL_AMPLITUDE
                         ? "WEAK_SIGNAL: shield sensor from room light"
                         : "SEARCHING: keep finger still for 2 beats";
    heartRateAlarm = false;
    abnormalHeartSince = 0;
    if (lastBeat != 0 && now - lastBeat > HEART_NO_BEAT_TIMEOUT_MS * 2) {
      lastBeat = 0;
      clearHeartIntervals();
    }
    return;
  }

  if (!heartRateValid) {
    heartRateError = heartIntervalsValid == 0
                         ? "STABILIZING: first pulse detected"
                         : "STABILIZING: measuring pulse intervals";
  }

  bool abnormal = heartRateValid &&
                  (heartRateBpm < HEART_RATE_LOW_BPM ||
                   heartRateBpm > HEART_RATE_HIGH_BPM);
  if (abnormal) {
    if (abnormalHeartSince == 0) abnormalHeartSince = now;
    heartRateAlarm = now - abnormalHeartSince >= HEART_ALARM_CONFIRM_MS;
  } else {
    abnormalHeartSince = 0;
    heartRateAlarm = false;
  }
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
  data["fall_state"] = mpuValid ? fallStateName() : "SENSOR_ERROR";
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

  String out;
  serializeJson(data, out);
  return out;
}

// ---------- HTTP POST ----------
void sendJSON(const String &jsonMessage) {
  if (authRetryAt && (int32_t)(millis() - authRetryAt) < 0) return;
  if (WiFi.status() != WL_CONNECTED) {
    remoteBuzzerRequested = false;
    Serial.println("[CareLink] Upload skipped: WiFi disconnected");
    return;
  }

  // Never downgrade to HTTP or skip certificate/hostname verification.
  String url = serverUrl();
  int pathStart = url.indexOf('/', 8);
  time_t signedTime = time(nullptr);
  if (!url.startsWith("https://") || pathStart < 0 || url.substring(pathStart) != "/sensor-data") {
    remoteBuzzerRequested = false;
    Serial.println("[CareLink] Upload skipped: endpoint must be exactly https://HOST:PORT/sensor-data");
    scheduleAuthRetry();
    return;
  }
  // Nonblocking SNTP: never invent a time or disable TLS validity checks.
  if (!carelink::uploadClockReady(authClockSynchronized, (int64_t)signedTime,
                                 (uint32_t)millis(), (uint32_t)authClockLastSync)) {
    remoteBuzzerRequested = false;
    Serial.println("[CareLink] Upload skipped: waiting for recent SNTP synchronization; no POST sent");
    scheduleAuthRetry();
    return;
  }
  Serial.printf("[CareLink] Sensor payload prepared: %u bytes\n", (unsigned)jsonMessage.length());
  uint8_t randomNonce[16]; char nonce[33], timestamp[24], signature[65];
  esp_fill_random(randomNonce, sizeof(randomNonce)); // WiFi is active: hardware RNG entropy is enabled.
  carelink::hex(randomNonce, sizeof(randomNonce), nonce);
  snprintf(timestamp, sizeof(timestamp), "%lld", (long long)signedTime);
  if (strlen(DEVICE_API_KEY) < 32 || strlen(DEVICE_API_KEY) > 128 ||
      !carelink::signature(DEVICE_AUTH_ID, timestamp, nonce,
                          (const uint8_t *)jsonMessage.c_str(), jsonMessage.length(),
                          DEVICE_HMAC_KEY_HEX, authSHA256, authHMAC256, signature)) {
    remoteBuzzerRequested = false;
    Serial.println("[CareLink] Upload skipped: invalid local device authentication configuration");
    scheduleAuthRetry();
    return;
  }
  Serial.println("[CareLink] HMAC signing completed");
  WiFiClientSecure client;
  client.setCACert(GATEWAY_ROOT_CA);
  client.setHandshakeTimeout(8);

  HTTPClient http;
  http.setConnectTimeout(8000);
  http.setTimeout(HTTP_TIMEOUT_MS);
  http.setFollowRedirects(HTTPC_DISABLE_FOLLOW_REDIRECTS);
  if (!http.begin(client, url)) {
    remoteBuzzerRequested = false;
    Serial.println("[CareLink] Upload skipped: HTTPS client initialization failed");
    scheduleAuthRetry();
    return;
  }
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-CareLink-Device-Id", DEVICE_AUTH_ID);
  http.addHeader("X-CareLink-Api-Key", DEVICE_API_KEY);
  http.addHeader("X-CareLink-Timestamp", timestamp);
  http.addHeader("X-CareLink-Nonce", nonce);
  http.addHeader("X-CareLink-Signature", signature);
  // Never log authentication headers or keys. The exact signed JSON bytes follow.

  Serial.println("[CareLink] HTTPS POST started");
  int code = http.POST(jsonMessage);
  if (code > 0) {
    Serial.printf("HTTPS POST status: %d\n", code);
    Serial.printf("[CareLink] HTTP response: %d\n", code);
    Serial.printf("[CareLink] %s\n", carelink::uploadHttpOutcome(code));
    String response = http.getString();
    if (code >= 200 && code < 300) { authRetryDelayMs = 1000; authRetryAt = 0; }
    else { scheduleAuthRetry(); }
    if (code >= 200 && code < 300 && response.length() > 0) {
      JsonDocument responseData;
      DeserializationError jsonError = deserializeJson(responseData, response);
      if (!jsonError) {
        const char *classification =
            responseData["classification"] | "unavailable";
        snprintf(serverClassification, sizeof(serverClassification), "%s",
                 classification);
        serverConfidence = responseData["confidence"] | 0.0f;
        remoteBuzzerRequested = strcmp(classification, "warning") == 0 ||
                                strcmp(classification, "critical") == 0;
        lastServerResponse = millis();
      } else {
        remoteBuzzerRequested = false;
        Serial.printf("Response JSON error: %s\n", jsonError.c_str());
      }
    } else {
      remoteBuzzerRequested = false;
    }
  } else {
    remoteBuzzerRequested = false;
    char tlsError[128] = {0};
    int tlsCode = client.lastError(tlsError, sizeof(tlsError));
    // Report numeric library errors, never raw responses, keys or headers.
    if (tlsCode == MBEDTLS_ERR_X509_CERT_VERIFY_FAILED)
      Serial.println("[CareLink] TLS verification failed: check CA, SAN and clock");
    else if (code == HTTPC_ERROR_READ_TIMEOUT)
      Serial.println("[CareLink] Connection timeout");
    else
      Serial.println("[CareLink] Network/TLS connection failed: check hotspot, Mac IP, listener and CA");
    Serial.printf("[CareLink] Transport error: HTTPClient=%d TLS=%d; no HTTP response\n", code, tlsCode);
    scheduleAuthRetry();
  }
  http.end();
}

// ---------- Setup ----------
void setup() {
  Serial.begin(115200);
  delay(1000);

  analogReadResolution(12);
  pinMode(HEART_RATE_PIN, INPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);
  initLCD();

  scanTargetWiFi();
  connectWiFi();

  Wire.begin(MPU_SDA, MPU_SCL);
  Wire.setClock(100000);
  Wire.setTimeOut(10);

  mpuReady = mpu.begin(0x68, &Wire);
  if (!mpuReady) {
    mpuAddress = 0x69;
    mpuReady = mpu.begin(mpuAddress, &Wire);
  }

  if (mpuReady) {
    mpu.setAccelerometerRange(MPU6050_RANGE_8_G);
    mpu.setGyroRange(MPU6050_RANGE_500_DEG);
    mpu.setFilterBandwidth(MPU6050_BAND_44_HZ);
    mpu.setSampleRateDivisor(9);
    mpuValid = readMPUAcceleration();
  } else {
    mpuError = "NOT_FOUND: check SDA=21, SCL=22 and power";
  }

  updateMLX();
  lastTemperatureRead = millis();
  lastLcdUpdate = millis() - LCD_UPDATE_INTERVAL_MS;
  updateLCD(millis());
}

// ---------- Loop ----------
void loop() {
  unsigned long now = millis();

  // Log outside the SNTP callback and never invent a replacement clock.
  if (authClockSynchronized && !authClockReported) {
    authClockReported = true;
    Serial.printf("[CareLink] SNTP synchronized: epoch=%lld\n", (long long)time(nullptr));
  }

  updateHeartRate(now);

  static unsigned long lastWifiCheck = 0;
  if (now - lastWifiCheck >= 5000) {
    lastWifiCheck = now;
    if (WiFi.status() != WL_CONNECTED) {
      Serial.println("WiFi lost, reconnecting...");
      WiFi.disconnect();
      scanTargetWiFi();
      connectWiFi();
    }
  }

  if (mpuReady && now - lastSample >= SAMPLE_INTERVAL_MS) {
    lastSample = now;
    mpuValid = readMPUAcceleration();
    if (mpuValid && totalG > peakG) peakG = totalG;
    updateFallDetector(now);
  }

  if (now - lastTemperatureRead >= TEMPERATURE_INTERVAL_MS) {
    lastTemperatureRead = now;
    updateMLX();
  }

  updateBuzzer(now);
  updateLCD(now);

  if (now - lastPrint >= PRINT_INTERVAL_MS) {
    lastPrint = now;
    Serial.println(buildJSON());
  }

  if (now - lastSend >= SEND_INTERVAL_MS) {
    lastSend = now;
    sendJSON(buildJSON());
    peakG = 0.0f;
  }

  delay(1);
}
