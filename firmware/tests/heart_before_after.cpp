// Baseline processor from upstream commit 1592530fe49dac7883d99e9cfd32a3b256d8114e.
// Synthetic waveform replay; this is not a hardware measurement.
#include <cmath>
#include <algorithm>
#include <cstdint>
#include <iostream>
#include <vector>
#include <iomanip>
#include "../elder_sensors/heart_rate_processor.h"
namespace legacy {
uint32_t clockMs=0;int input=0; const int HEART_RATE_PIN=34;
uint32_t millis(){return clockMs;} int analogRead(int){return input;}
template<class T>T constrain(T v,T a,T b){return std::max(a,std::min(v,b));}
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


}
int main(int argc,char**argv){
 const bool low=argc>1&&std::string(argv[1])=="low";
 HeartRateProcessor improved;
 uint32_t oldFirst=0,newFirst=0,oldChange=0,newChange=0;
 double oldError=0,newError=0;int oldCount=0,newCount=0;
 for(uint32_t t=2;t<=25000;t+=2){
  const float bpm=t<15000?75:120;
  float phase=t<15000?t/1000.f*75/60:(t-15000)/1000.f*120/60+18.75;
  int raw=(low?1000:2200)+60*std::sin(phase*6.283185307f)+12*std::sin(t/1000.f*50*6.283185307f);
  legacy::clockMs=t;legacy::input=raw;legacy::updateHeartRate(t);
  improved.sample(raw,t);auto n=improved.snapshot(t);
  if(legacy::heartRateValid&&!oldFirst)oldFirst=t;
  if(n.valid&&!newFirst)newFirst=t;
  if(t>=15000 && legacy::heartRateValid && std::fabs(legacy::heartRateBpm-120)<5 && !oldChange)oldChange=t-15000;
  if(t>=15000 && n.valid && std::fabs(n.bpm-120)<5 && !newChange)newChange=t-15000;
  if(t>=5000&&t<14000&&t%1000==0){
   if(legacy::heartRateValid){oldError+=std::fabs(legacy::heartRateBpm-75);oldCount++;}
   if(n.valid){newError+=std::fabs(n.bpm-75);newCount++;}
  }
 }
 std::cout<<"{\"scenario\":\""<<(low?"low_dc_1000":"dc_2200")<<"\",\"old_first_ms\":"<<oldFirst<<",\"new_first_ms\":"<<newFirst<<",\"old_rate_change_ms\":"<<oldChange<<",\"new_rate_change_ms\":"<<newChange<<",\"old_valid_1s_samples\":"<<oldCount<<",\"new_valid_1s_samples\":"<<newCount<<",\"old_mae_bpm\":"<<(oldCount?oldError/oldCount:-1)<<",\"new_mae_bpm\":"<<(newCount?newError/newCount:-1)<<"}\n";
}
