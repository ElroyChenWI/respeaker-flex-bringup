// reSpeaker Flex XVF3800 <-> XIAO ESP32S3 wiring.
// Source: Seeed wiki (reSpeaker_flex_i2s_test.md / reSpeaker_flex_gpio.md), see docs/hardware.md.
#pragma once

// I2C control bus (Wire default pins on XIAO ESP32S3: D4/D5)
#define PIN_I2C_SDA 5
#define PIN_I2C_SCL 6
#define I2C_FREQ_HZ 100000

#define XVF3800_I2C_ADDR 0x2C  // XMOS control servicer
#define AIC3104_I2C_ADDR 0x18  // TI codec on core board

// I2S: ESP32 is master (Flex i2s firmware = I2S slave image)
#define PIN_I2S_BCK  8
#define PIN_I2S_WS   7
#define PIN_I2S_DOUT 44  // ESP32 -> XVF3800 (playback / AEC reference)
#define PIN_I2S_DIN  43  // XVF3800 -> ESP32 (processed mic audio)

#define I2S_DEFAULT_RATE 16000  // must match flashed XVF image: *_16k* or *_48k*
#define I2S_SLOT_BITS    32
#define I2S_CHANNELS     2
