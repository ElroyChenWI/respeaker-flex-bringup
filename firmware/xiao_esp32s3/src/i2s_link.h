// Full-duplex I2S link to XVF3800, 32-bit stereo slots. Default role: slave (see board_pins.h).
#pragma once
#include <Arduino.h>

namespace i2s_link {

// master = ESP32 drives BCLK/WS; slave = XVF3800 drives them.
bool start(uint32_t rate, bool master);
void stop();
bool running();
bool is_master();
uint32_t rate();

// Reads up to `frames` stereo frames (int32 L,R interleaved). Returns frames read.
size_t read(int32_t *buf, size_t frames, uint32_t timeout_ms);
// Writes stereo frames. Returns frames written.
size_t write(const int32_t *buf, size_t frames, uint32_t timeout_ms);

}  // namespace i2s_link
