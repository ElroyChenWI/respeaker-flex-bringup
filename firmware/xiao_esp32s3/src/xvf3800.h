// XVF3800 control over I2C (XMOS device-control protocol).
//
// Write: [resid][cmdid][len][payload...]
// Read:  write [resid][cmdid|0x80][len+1], then read len+1 bytes; byte 0 = status.
//        status 0 = OK, 64 = servicer busy -> retry.
#pragma once
#include <Arduino.h>
#include <Wire.h>

namespace xvf {

constexpr uint8_t STATUS_OK = 0;
constexpr uint8_t STATUS_RETRY = 64;

enum Result : int {
  OK = 0,
  ERR_NACK = -1,      // I2C write not acknowledged
  ERR_SHORT = -2,     // fewer bytes than requested
  ERR_TIMEOUT = -3,   // still RETRY after max attempts
  ERR_STATUS = -4,    // non-zero, non-retry status byte
  ERR_ARG = -5,
};

void begin(TwoWire &wire, uint8_t addr);

// Reads `len` payload bytes into `out`. On ERR_STATUS, *status holds the device code.
int read(uint8_t resid, uint8_t cmdid, uint8_t *out, uint8_t len, uint8_t *status = nullptr);
int write(uint8_t resid, uint8_t cmdid, const uint8_t *data, uint8_t len);

const char *strerror(int rc);

}  // namespace xvf
