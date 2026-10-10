// XVF3800 firmware upgrade over I2C (XMOS DFU controller servicer, resid 0xF0).
//
// Follows the USB DFU 1.1 state machine (XMOS fwk_xvf "DFU operations"):
//   SETALTERNATE(1=upgrade) -> { DNLOAD [len_lo len_hi data[128]] ; poll GETSTATUS
//   until dfuDNLOAD_IDLE }* -> zero-length DNLOAD -> poll until manifest done -> DETACH.
// Only the upgrade partition is written; the factory image cannot be overwritten, and an
// invalid upgrade image makes the bootloader fall back to factory.
#pragma once
#include <Arduino.h>

namespace xvf_dfu {

constexpr uint8_t kResid = 0xF0;
constexpr uint16_t kBlockSize = 128;

enum State : uint8_t {
  APP_IDLE = 0, APP_DETACH = 1, DFU_IDLE = 2, DNLOAD_SYNC = 3, DNBUSY = 4, DNLOAD_IDLE = 5,
  MANIFEST_SYNC = 6, MANIFEST = 7, MANIFEST_WAIT_RESET = 8, UPLOAD_IDLE = 9, DFU_ERROR = 10,
};

struct Status {
  uint8_t status;    // DFU bStatus, 0 = OK
  uint32_t poll_ms;  // bwPollTimeout
  uint8_t state;     // State
};

int get_status(Status *st);
int begin(Status *st);                                    // clear errors, select upgrade partition
int block(const uint8_t *data, uint16_t len, Status *st);  // len 0 = end of image (manifest)
int abort_transfer();
int detach();  // reboot the XVF3800 into the new image

}  // namespace xvf_dfu
