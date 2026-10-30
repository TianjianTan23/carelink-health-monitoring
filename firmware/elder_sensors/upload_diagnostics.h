#pragma once
#include <stdint.h>

namespace carelink {
// Preserve the existing fail-closed clock policy, including millis rollover.
inline bool uploadClockReady(bool synchronized, int64_t epoch, uint32_t now,
                             uint32_t lastSync) {
  return synchronized && epoch >= 1704067200 &&
         (uint32_t)(now - lastSync) <= 21600000UL;
}
// Constant messages only; no response bodies or authentication headers.
inline const char *uploadHttpOutcome(int status) {
  if (status == 200) return "Upload accepted";
  if (status == 401 || status == 403) return "Authentication rejected";
  if (status == 409) return "Nonce rejected";
  if (status == 400 || status == 413 || status == 415 || status == 422)
    return "Invalid payload or endpoint";
  if (status == 404 || status == 405) return "Endpoint not found";
  if (status == 408 || status == 504) return "Connection timeout";
  if (status == 429) return "Rate limited";
  if (status >= 500) return "Server unavailable or write gate frozen";
  if (status >= 300 && status < 400) return "Redirect refused";
  return "Unexpected HTTP response; verify gateway endpoint";
}
}
