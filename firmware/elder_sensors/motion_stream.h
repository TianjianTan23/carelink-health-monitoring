#pragma once

#include <Arduino.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/queue.h>
#include <freertos/semphr.h>

constexpr uint16_t MOTION_CAPACITY = 420;
struct MotionSample {
  uint32_t timestampMs;
  float values[6];  // ax, ay, az (g), gx, gy, gz (degrees/second)
};
struct UploadJob {
  char *json;
  uint32_t createdAt;
};
struct ServerReply {
  bool ok;
  char classification[16];
  float confidence;
  uint32_t requestCreatedAt;
};
