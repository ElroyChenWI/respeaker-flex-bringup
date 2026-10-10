#include "xvf3800.h"

namespace xvf {

static TwoWire *s_wire = nullptr;
static uint8_t s_addr = 0;
static constexpr int kMaxAttempts = 100;
static constexpr uint8_t kMaxPayload = 200;  // Wire buffer is set to 256 bytes in setup()

void begin(TwoWire &wire, uint8_t addr) {
  s_wire = &wire;
  s_addr = addr;
}

int read(uint8_t resid, uint8_t cmdid, uint8_t *out, uint8_t len, uint8_t *status) {
  if (!s_wire || len == 0 || len > kMaxPayload) return ERR_ARG;
  uint8_t st = 0xFF;
  for (int attempt = 0; attempt < kMaxAttempts; ++attempt) {
    s_wire->beginTransmission(s_addr);
    s_wire->write(resid);
    s_wire->write(cmdid | 0x80);
    s_wire->write(len + 1);
    if (s_wire->endTransmission() != 0) return ERR_NACK;

    size_t n = s_wire->requestFrom(s_addr, (uint8_t)(len + 1));
    if (n < (size_t)(len + 1)) return ERR_SHORT;
    st = s_wire->read();
    for (uint8_t i = 0; i < len; ++i) out[i] = s_wire->read();
    if (status) *status = st;
    if (st == STATUS_OK) return OK;
    if (st != STATUS_RETRY) return ERR_STATUS;
    delay(1);
  }
  return ERR_TIMEOUT;
}

int write(uint8_t resid, uint8_t cmdid, const uint8_t *data, uint8_t len) {
  if (!s_wire || len > kMaxPayload) return ERR_ARG;
  s_wire->beginTransmission(s_addr);
  s_wire->write(resid);
  s_wire->write(cmdid);
  s_wire->write(len);
  s_wire->write(data, len);
  return s_wire->endTransmission() == 0 ? OK : ERR_NACK;
}

const char *strerror(int rc) {
  switch (rc) {
    case OK: return "ok";
    case ERR_NACK: return "i2c nack";
    case ERR_SHORT: return "short read";
    case ERR_TIMEOUT: return "retry timeout";
    case ERR_STATUS: return "bad status";
    case ERR_ARG: return "bad arg";
    default: return "unknown";
  }
}

}  // namespace xvf
