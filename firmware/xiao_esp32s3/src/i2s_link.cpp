#include "i2s_link.h"

#include <driver/i2s.h>

#include "board_pins.h"

namespace i2s_link {

static constexpr i2s_port_t kPort = I2S_NUM_0;
static bool s_running = false;
static uint32_t s_rate = 0;
static bool s_master = I2S_DEFAULT_MASTER;

bool start(uint32_t rate, bool master) {
  if (s_running) stop();

  i2s_config_t cfg = {};
  cfg.mode = (i2s_mode_t)((master ? I2S_MODE_MASTER : I2S_MODE_SLAVE) | I2S_MODE_RX | I2S_MODE_TX);
  cfg.sample_rate = rate;
  cfg.bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT;
  cfg.channel_format = I2S_CHANNEL_FMT_RIGHT_LEFT;
  cfg.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  cfg.intr_alloc_flags = 0;
  cfg.dma_buf_count = 8;
  cfg.dma_buf_len = 512;  // frames; 8 x 512 = 256 ms @16k
  cfg.use_apll = false;
  cfg.tx_desc_auto_clear = true;  // send silence when nothing is queued

  if (i2s_driver_install(kPort, &cfg, 0, nullptr) != ESP_OK) return false;

  i2s_pin_config_t pins = {};
  pins.mck_io_num = I2S_PIN_NO_CHANGE;
  pins.bck_io_num = PIN_I2S_BCK;
  pins.ws_io_num = PIN_I2S_WS;
  pins.data_out_num = PIN_I2S_DOUT;
  pins.data_in_num = PIN_I2S_DIN;
  if (i2s_set_pin(kPort, &pins) != ESP_OK) {
    i2s_driver_uninstall(kPort);
    return false;
  }
  i2s_zero_dma_buffer(kPort);
  s_running = true;
  s_rate = rate;
  s_master = master;
  return true;
}

void stop() {
  if (!s_running) return;
  i2s_driver_uninstall(kPort);
  s_running = false;
  s_rate = 0;
}

bool running() { return s_running; }
bool is_master() { return s_master; }
uint32_t rate() { return s_rate; }

size_t read(int32_t *buf, size_t frames, uint32_t timeout_ms) {
  if (!s_running) return 0;
  size_t got = 0;
  i2s_read(kPort, buf, frames * 2 * sizeof(int32_t), &got, pdMS_TO_TICKS(timeout_ms));
  return got / (2 * sizeof(int32_t));
}

size_t write(const int32_t *buf, size_t frames, uint32_t timeout_ms) {
  if (!s_running) return 0;
  size_t put = 0;
  i2s_write(kPort, buf, frames * 2 * sizeof(int32_t), &put, pdMS_TO_TICKS(timeout_ms));
  return put / (2 * sizeof(int32_t));
}

}  // namespace i2s_link
