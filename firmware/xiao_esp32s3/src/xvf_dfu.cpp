#include "xvf_dfu.h"

#include "xvf3800.h"

namespace xvf_dfu {

enum Cmd : uint8_t {
  CMD_DETACH = 0, CMD_DNLOAD = 1, CMD_GETSTATUS = 3, CMD_CLRSTATUS = 4, CMD_ABORT = 6,
  CMD_SETALTERNATE = 64,
};
static constexpr uint32_t kPollLimitMs = 5000;

static int write1(uint8_t cmd, uint8_t value) { return xvf::write(kResid, cmd, &value, 1); }

int get_status(Status *st) {
  uint8_t p[5];
  int rc = xvf::read(kResid, CMD_GETSTATUS, p, sizeof(p));
  if (rc != xvf::OK) return rc;
  st->status = p[0];
  st->poll_ms = p[1] | (p[2] << 8) | ((uint32_t)p[3] << 16);
  st->state = p[4];
  return xvf::OK;
}

int abort_transfer() { return write1(CMD_ABORT, 0); }
int detach() { return write1(CMD_DETACH, 0); }

int begin(Status *st) {
  int rc;
  if ((rc = abort_transfer()) != xvf::OK) return rc;
  if ((rc = write1(CMD_CLRSTATUS, 0)) != xvf::OK) return rc;
  if ((rc = write1(CMD_SETALTERNATE, 1)) != xvf::OK) return rc;
  return get_status(st);
}

int block(const uint8_t *data, uint16_t len, Status *st) {
  if (len > kBlockSize) return xvf::ERR_ARG;
  uint8_t payload[2 + kBlockSize];
  memset(payload, 0xFF, sizeof(payload));
  payload[0] = len & 0xFF;
  payload[1] = len >> 8;
  if (len) memcpy(&payload[2], data, len);
  int rc = xvf::write(kResid, CMD_DNLOAD, payload, sizeof(payload));
  if (rc != xvf::OK) return rc;

  // DFU 1.1: GETSTATUS drives DNLOAD_SYNC -> DNBUSY -> DNLOAD_IDLE (or the manifest states).
  const uint32_t t0 = millis();
  while (millis() - t0 < kPollLimitMs) {
    if ((rc = get_status(st)) != xvf::OK) return rc;
    if (st->state == DFU_ERROR || st->status != 0) return xvf::ERR_STATUS;
    if (len && st->state == DNLOAD_IDLE) return xvf::OK;
    if (!len && (st->state == DFU_IDLE || st->state == MANIFEST_WAIT_RESET)) return xvf::OK;
    delay(st->poll_ms ? min<uint32_t>(st->poll_ms, 100) : 1);
  }
  return xvf::ERR_TIMEOUT;
}

}  // namespace xvf_dfu
