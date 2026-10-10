// Full-duplex I2S link to XVF3800. ESP32 = master, 32-bit stereo slots.
#pragma once
#include <Arduino.h>

namespace i2s_link {

bool start(uint32_t rate);
void stop();
bool running();
uint32_t rate();

// Reads up to `frames` stereo frames (int32 L,R interleaved). Returns frames read.
size_t read(int32_t *buf, size_t frames, uint32_t timeout_ms);
// Writes stereo frames. Returns frames written.
size_t write(const int32_t *buf, size_t frames, uint32_t timeout_ms);

}  // namespace i2s_link
