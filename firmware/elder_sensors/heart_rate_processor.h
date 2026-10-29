#pragma once
#include <cmath>
#include <cstdint>
#include <algorithm>

// KY-039 optical waveform processing. No Arduino dependencies: exercise this
// same implementation with synthetic waveforms on the host before flashing.
struct HeartSnapshot {
  float bpm = NAN, displayBpm = NAN, amplitude = 0, filtered = 0;
  int raw = 0;
  bool valid = false, held = false, contact = false;
  uint8_t quality = 0;
  uint32_t lastValidAt = 0, sampleCount = 0, gapCount = 0;
  const char *state = "ACQUIRING";
};

class HeartRateProcessor {
 public:
  // Sample at 500 Hz; process non-overlapping 20 ms means (50 Hz).
  // BPM updates on accepted beats, independently of the 1 s HTTP upload.
  void sample(int raw, uint32_t now) {
    ++out.sampleCount;
    if (started && now - lastSample > 12) {
      ++out.gapCount;
      resetWave(now);
      sum = 0; count = 0; blockAt = now;
    }
    if (!started) { started = true; blockAt = now; settleUntil = now + 600; }
    lastSample = now;
    sum += raw; ++count;
    if (now - blockAt < 20) { updateFreshness(now); return; }
    const float mean = static_cast<float>(sum) / count;
    sum = 0; count = 0; blockAt = now;
    process(mean, now);
    updateFreshness(now);
  }

  HeartSnapshot snapshot(uint32_t now) {
    updateFreshness(now);
    return out;
  }

 private:
  HeartSnapshot out;
  bool started = false, initialized = false, armed = true;
  uint32_t lastSample = 0, blockAt = 0, sum = 0, count = 0;
  uint32_t settleUntil = 0, lastCandidate = 0;
  uint32_t intervals[3] = {}, intervalCount = 0, intervalIndex = 0;
  uint32_t changedInterval = 0, changeCount = 0;
  float baseline = 0, filtered = 0, envelope = 0, previousMean = 0;

  static bool elapsed(uint32_t now, uint32_t deadline) {
    return static_cast<int32_t>(now - deadline) >= 0;
  }
  float medianInterval() const {
    if (!intervalCount) return 0;
    uint32_t values[3];
    for (uint32_t i = 0; i < intervalCount; ++i) values[i] = intervals[i];
    std::sort(values, values + intervalCount);
    return intervalCount == 2 ? (values[0] + values[1]) * .5f : values[intervalCount / 2];
  }
  void resetWave(uint32_t now) {
    initialized = false; armed = true; lastCandidate = 0;
    intervalCount = intervalIndex = changeCount = 0;
    baseline = filtered = envelope = 0;
    settleUntil = now + 600;
    out.valid = false; out.bpm = NAN; out.quality = 0;
  }
  void acceptInterval(uint32_t interval, uint32_t now, bool restart) {
    if (restart) { intervalCount = intervalIndex = 0; }
    intervals[intervalIndex] = interval;
    intervalIndex = (intervalIndex + 1) % 3;
    if (intervalCount < 3) ++intervalCount;
    const float bpm = 60000.0f / medianInterval();
    // Median of three rejects a single bad interval; modest smoothing limits
    // display jitter. A sustained rhythm change resets this filter promptly.
    out.displayBpm = (!std::isfinite(out.displayBpm) || restart || !out.valid)
        ? bpm : out.displayBpm * .65f + bpm * .35f;
    out.lastValidAt = now;
    out.valid = true; out.bpm = out.displayBpm; out.state = "TRACKING";
    changeCount = 0;
  }
  void beat(uint32_t now) {
    if (!lastCandidate) { lastCandidate = now; return; }
    const uint32_t interval = now - lastCandidate;
    // Refractory period prevents counting the same pulse/dicrotic notch twice.
    if (interval < 300) return;
    lastCandidate = now;
    if (interval > 2000) {
      intervalCount = intervalIndex = changeCount = 0;
      out.valid = false; out.state = "ACQUIRING"; return;
    }
    const float reference = medianInterval();
    if (!reference || std::fabs(interval - reference) <= std::max(100.0f, reference * .25f)) {
      acceptInterval(interval, now, false);
    } else {
      // Two consistent new intervals can represent a real rate change.
      // Never freeze at the old rate, or invent a missed beat by halving an IBI.
      if (changeCount && std::fabs(static_cast<float>(interval) - changedInterval)
          <= std::max(80.0f, changedInterval * .18f)) ++changeCount;
      else changeCount = 1;
      changedInterval = interval;
      out.state = "REACQUIRING";
      if (changeCount >= 2) acceptInterval(interval, now, true);
    }
  }
  void process(float mean, uint32_t now) {
    out.raw = static_cast<int>(std::lround(mean));
    if (mean <= 5 || mean >= 4090) {
      resetWave(now); out.contact = false; out.state = "ADC_SATURATED"; return;
    }
    if (initialized && std::fabs(mean - previousMean) > 250) {
      resetWave(now); out.state = "MOTION_OR_CONTACT_CHANGE";
    }
    previousMean = mean;
    if (!initialized) { baseline = mean; initialized = true; }
    baseline += .025f * (mean - baseline);
    filtered += .5f * ((mean - baseline) - filtered);
    envelope = std::max(std::fabs(filtered), envelope * .97f);
    out.filtered = filtered; out.amplitude = envelope;
    // No hard-coded DC finger threshold: board polarity and room light vary.
    out.contact = envelope >= 4;
    if (!elapsed(now, settleUntil)) { out.state = "SETTLING"; return; }
    const float threshold = std::max(4.0f, envelope * .5f);
    if (filtered < threshold * .2f) armed = true;
    if (armed && filtered >= threshold) { armed = false; beat(now); }
    out.quality = static_cast<uint8_t>(std::min(100.0f,
        std::max(0.0f, (envelope - 4) * 2 + intervalCount * 20.0f)));
    if (!out.contact) out.state = "WEAK_SIGNAL";
  }
  void updateFreshness(uint32_t now) {
    const uint32_t age = now - out.lastValidAt;
    if (!out.lastValidAt || age > 3000) {
      out.valid = false; out.bpm = NAN;
    }
    out.held = !out.valid && std::isfinite(out.displayBpm) && age <= 30000;
    if (age > 30000) out.displayBpm = NAN;
  }
};
