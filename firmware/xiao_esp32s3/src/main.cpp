// reSpeaker Flex XVF3800 EVK bring-up shell (XIAO ESP32S3).
//
// Line-based text protocol over USB-Serial/JTAG. Every command ends with exactly
// one line starting with "OK" or "ERR". `rec` additionally sends a binary block:
//   REC rate=<hz> ch=2 bits=<16|32> bytes=<n>\n  <n raw bytes>  \nOK rec ...\n
// Host tools in host/ speak this protocol.
#include <Arduino.h>
#include <Wire.h>
#include <math.h>

#include "board_pins.h"
#include "i2s_link.h"
#include "xvf3800.h"

#ifndef EVK_FW_VERSION
#define EVK_FW_VERSION "dev"
#endif

static constexpr size_t kChunkFrames = 512;
static int32_t s_buf[kChunkFrames * 2];
static char s_line[160];
static size_t s_line_len = 0;

// ---------- helpers ----------

static int split(char *line, char **argv, int max_args) {
  int argc = 0;
  for (char *tok = strtok(line, " \t"); tok && argc < max_args; tok = strtok(nullptr, " \t")) {
    argv[argc++] = tok;
  }
  return argc;
}

static bool parse_u32(const char *s, uint32_t *out) {
  char *end = nullptr;
  unsigned long v = strtoul(s, &end, 0);  // accepts 0x..
  if (!s[0] || *end) return false;
  *out = v;
  return true;
}

static void reply_err(const char *what) { Serial.printf("ERR %s\n", what); }

static bool require_i2s() {
  if (i2s_link::running()) return true;
  reply_err("i2s not started (run: i2s start)");
  return false;
}

// ---------- commands ----------

static void cmd_help() {
  Serial.println("# commands:");
  Serial.println("#  info                     firmware/chip info");
  Serial.println("#  i2cscan                  list I2C devices");
  Serial.println("#  ver                      XVF3800 VERSION");
  Serial.println("#  doa                      XVF3800 DOA_VALUE");
  Serial.println("#  xr <resid> <cmd> <n>     raw control read, n payload bytes");
  Serial.println("#  xw <resid> <cmd> <b...>  raw control write, payload bytes");
  Serial.println("#  i2s start [rate] | stop  start/stop I2S master");
  Serial.println("#  stat [ms]                capture and report per-channel level");
  Serial.println("#  rec <ms> [16|32]         stream raw PCM (binary block)");
  Serial.println("#  tone <hz> <ms> [dbfs]    play sine to XVF3800 I2S input");
  Serial.println("OK help");
}

static void cmd_info() {
  Serial.printf("# evk_fw=%s chip=%s rev=%d cpu=%uMHz flash=%u psram=%u\n", EVK_FW_VERSION,
                ESP.getChipModel(), ESP.getChipRevision(), ESP.getCpuFreqMHz(),
                ESP.getFlashChipSize(), ESP.getPsramSize());
  Serial.printf("# pins i2c sda=%d scl=%d | i2s bck=%d ws=%d dout=%d din=%d\n", PIN_I2C_SDA,
                PIN_I2C_SCL, PIN_I2S_BCK, PIN_I2S_WS, PIN_I2S_DOUT, PIN_I2S_DIN);
  Serial.printf("OK info i2s=%s rate=%u\n", i2s_link::running() ? "on" : "off", i2s_link::rate());
}

static void cmd_i2cscan() {
  int found = 0;
  for (uint8_t a = 0x08; a < 0x78; ++a) {
    Wire.beginTransmission(a);
    if (Wire.endTransmission() == 0) {
      const char *name = a == XVF3800_I2C_ADDR ? "xvf3800" : a == AIC3104_I2C_ADDR ? "aic3104" : "?";
      Serial.printf("# 0x%02X %s\n", a, name);
      ++found;
    }
  }
  Serial.printf("OK i2cscan found=%d\n", found);
}

static void cmd_ver() {
  uint8_t v[3];
  uint8_t st = 0;
  int rc = xvf::read(48, 0, v, sizeof(v), &st);
  if (rc != xvf::OK) {
    Serial.printf("ERR ver %s status=%u\n", xvf::strerror(rc), st);
    return;
  }
  Serial.printf("OK ver %u.%u.%u\n", v[0], v[1], v[2]);
}

static void cmd_doa() {
  uint8_t p[4];
  uint8_t st = 0;
  int rc = xvf::read(20, 18, p, sizeof(p), &st);
  if (rc != xvf::OK) {
    Serial.printf("ERR doa %s status=%u\n", xvf::strerror(rc), st);
    return;
  }
  uint16_t deg = p[0] | (p[1] << 8);
  uint16_t speech = p[2] | (p[3] << 8);
  Serial.printf("OK doa deg=%u speech=%u\n", deg, speech);
}

static void cmd_xr(int argc, char **argv) {
  uint32_t resid, cmd, n;
  if (argc != 4 || !parse_u32(argv[1], &resid) || !parse_u32(argv[2], &cmd) ||
      !parse_u32(argv[3], &n) || resid > 255 || cmd > 127 || n == 0 || n > 120) {
    reply_err("usage: xr <resid> <cmd 0..127> <n 1..120>");
    return;
  }
  uint8_t out[120];
  uint8_t st = 0;
  int rc = xvf::read(resid, cmd, out, n, &st);
  if (rc != xvf::OK) {
    Serial.printf("ERR xr %s status=%u\n", xvf::strerror(rc), st);
    return;
  }
  Serial.print("OK xr");
  for (uint32_t i = 0; i < n; ++i) Serial.printf(" %02X", out[i]);
  Serial.println();
}

static void cmd_xw(int argc, char **argv) {
  uint32_t resid, cmd;
  if (argc < 3 || !parse_u32(argv[1], &resid) || !parse_u32(argv[2], &cmd) || resid > 255 ||
      cmd > 127 || argc - 3 > 120) {
    reply_err("usage: xw <resid> <cmd 0..127> <byte...>");
    return;
  }
  uint8_t data[120];
  int n = argc - 3;
  for (int i = 0; i < n; ++i) {
    uint32_t b;
    if (!parse_u32(argv[3 + i], &b) || b > 255) {
      reply_err("payload must be bytes 0..255");
      return;
    }
    data[i] = b;
  }
  int rc = xvf::write(resid, cmd, data, n);
  if (rc != xvf::OK) {
    Serial.printf("ERR xw %s\n", xvf::strerror(rc));
    return;
  }
  Serial.printf("OK xw n=%d\n", n);
}

static void cmd_i2s(int argc, char **argv) {
  if (argc >= 2 && !strcmp(argv[1], "stop")) {
    i2s_link::stop();
    Serial.println("OK i2s stopped");
    return;
  }
  if (argc >= 2 && !strcmp(argv[1], "start")) {
    uint32_t rate = I2S_DEFAULT_RATE;
    if (argc >= 3 && (!parse_u32(argv[2], &rate) || (rate != 16000 && rate != 48000))) {
      reply_err("rate must be 16000 or 48000");
      return;
    }
    if (!i2s_link::start(rate)) {
      reply_err("i2s start failed");
      return;
    }
    Serial.printf("OK i2s started rate=%u\n", rate);
    return;
  }
  reply_err("usage: i2s start [rate] | i2s stop");
}

static void cmd_stat(int argc, char **argv) {
  if (!require_i2s()) return;
  uint32_t ms = 1000;
  if (argc >= 2 && (!parse_u32(argv[1], &ms) || ms == 0 || ms > 10000)) {
    reply_err("ms must be 1..10000");
    return;
  }
  const uint32_t want = (uint64_t)i2s_link::rate() * ms / 1000;
  double sumsq[2] = {0, 0};
  int64_t peak[2] = {0, 0};
  uint32_t nonzero[2] = {0, 0};
  uint32_t got = 0;
  while (got < want) {
    size_t n = i2s_link::read(s_buf, min<uint32_t>(kChunkFrames, want - got), 100);
    if (n == 0) break;
    for (size_t i = 0; i < n; ++i) {
      for (int c = 0; c < 2; ++c) {
        int64_t s = s_buf[i * 2 + c];
        sumsq[c] += (double)s * (double)s;
        int64_t a = s < 0 ? -s : s;
        if (a > peak[c]) peak[c] = a;
        if (s != 0 && s != -1) ++nonzero[c];
      }
    }
    got += n;
  }
  if (got == 0) {
    reply_err("stat no samples (BCLK running? XVF in I2S slave image?)");
    return;
  }
  const double fs = 2147483648.0;
  Serial.print("OK stat");
  Serial.printf(" frames=%u", got);
  for (int c = 0; c < 2; ++c) {
    double rms = sqrt(sumsq[c] / got);
    double rms_db = rms > 0 ? 20.0 * log10(rms / fs) : -999.0;
    double pk_db = peak[c] > 0 ? 20.0 * log10((double)peak[c] / fs) : -999.0;
    Serial.printf(" %c_rms_dbfs=%.1f %c_peak_dbfs=%.1f %c_nonzero=%u", c ? 'R' : 'L', rms_db,
                  c ? 'R' : 'L', pk_db, c ? 'R' : 'L', nonzero[c]);
  }
  Serial.println();
}

static void cmd_rec(int argc, char **argv) {
  if (!require_i2s()) return;
  uint32_t ms = 0, bits = 16;
  if (argc < 2 || !parse_u32(argv[1], &ms) || ms == 0 || ms > 600000 ||
      (argc >= 3 && (!parse_u32(argv[2], &bits) || (bits != 16 && bits != 32)))) {
    reply_err("usage: rec <ms 1..600000> [16|32]");
    return;
  }
  const uint32_t frames = (uint64_t)i2s_link::rate() * ms / 1000;
  const uint32_t bytes = frames * 2 * (bits / 8);
  Serial.printf("REC rate=%u ch=2 bits=%u bytes=%u\n", i2s_link::rate(), bits, bytes);

  static int16_t out16[kChunkFrames * 2];
  uint32_t sent = 0, short_frames = 0;
  while (sent < frames) {
    size_t want = min<uint32_t>(kChunkFrames, frames - sent);
    size_t n = i2s_link::read(s_buf, want, 200);
    if (n < want) {  // keep the byte count exact; pad and report
      memset(&s_buf[n * 2], 0, (want - n) * 2 * sizeof(int32_t));
      short_frames += want - n;
    }
    if (bits == 32) {
      Serial.write((const uint8_t *)s_buf, want * 2 * sizeof(int32_t));
    } else {
      for (size_t i = 0; i < want * 2; ++i) out16[i] = (int16_t)(s_buf[i] >> 16);
      Serial.write((const uint8_t *)out16, want * 2 * sizeof(int16_t));
    }
    sent += want;
  }
  Serial.flush();
  Serial.printf("\nOK rec frames=%u padded=%u\n", frames, short_frames);
}

static void cmd_tone(int argc, char **argv) {
  if (!require_i2s()) return;
  uint32_t hz = 0, ms = 0;
  float dbfs = -20.0f;
  if (argc < 3 || !parse_u32(argv[1], &hz) || !parse_u32(argv[2], &ms) || hz == 0 ||
      hz >= i2s_link::rate() / 2 || ms == 0 || ms > 60000) {
    reply_err("usage: tone <hz> <ms 1..60000> [dbfs<=0]");
    return;
  }
  if (argc >= 4) dbfs = atof(argv[3]);
  if (dbfs > 0) dbfs = 0;
  const double amp = 2147483647.0 * pow(10.0, dbfs / 20.0);
  const double step = 2.0 * M_PI * hz / i2s_link::rate();
  const uint32_t frames = (uint64_t)i2s_link::rate() * ms / 1000;
  double phase = 0;
  uint32_t done = 0;
  while (done < frames) {
    size_t n = min<uint32_t>(kChunkFrames, frames - done);
    for (size_t i = 0; i < n; ++i) {
      int32_t s = (int32_t)(amp * sin(phase));
      s_buf[i * 2] = s;
      s_buf[i * 2 + 1] = s;
      phase += step;
      if (phase > 2.0 * M_PI) phase -= 2.0 * M_PI;
    }
    i2s_link::write(s_buf, n, 500);
    done += n;
  }
  Serial.printf("OK tone hz=%u ms=%u dbfs=%.1f\n", hz, ms, dbfs);
}

static void dispatch(char *line) {
  char *argv[128];
  int argc = split(line, argv, 128);
  if (argc == 0) return;
  const char *c = argv[0];
  if (!strcmp(c, "help")) cmd_help();
  else if (!strcmp(c, "info")) cmd_info();
  else if (!strcmp(c, "i2cscan")) cmd_i2cscan();
  else if (!strcmp(c, "ver")) cmd_ver();
  else if (!strcmp(c, "doa")) cmd_doa();
  else if (!strcmp(c, "xr")) cmd_xr(argc, argv);
  else if (!strcmp(c, "xw")) cmd_xw(argc, argv);
  else if (!strcmp(c, "i2s")) cmd_i2s(argc, argv);
  else if (!strcmp(c, "stat")) cmd_stat(argc, argv);
  else if (!strcmp(c, "rec")) cmd_rec(argc, argv);
  else if (!strcmp(c, "tone")) cmd_tone(argc, argv);
  else Serial.printf("ERR unknown command '%s' (try: help)\n", c);
}

// ---------- arduino ----------

void setup() {
  Serial.setTxBufferSize(16384);
  Serial.begin(115200);
  Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL, I2C_FREQ_HZ);
  xvf::begin(Wire, XVF3800_I2C_ADDR);
  // I2S stays off until asked: bring-up stages are gated one at a time.
  delay(200);
  Serial.printf("# reSpeaker Flex EVK fw %s ready (type 'help')\n", EVK_FW_VERSION);
}

void loop() {
  while (Serial.available()) {
    char ch = Serial.read();
    if (ch == '\r') continue;
    if (ch == '\n') {
      s_line[s_line_len] = '\0';
      dispatch(s_line);
      s_line_len = 0;
    } else if (s_line_len < sizeof(s_line) - 1) {
      s_line[s_line_len++] = ch;
    }
  }
}
