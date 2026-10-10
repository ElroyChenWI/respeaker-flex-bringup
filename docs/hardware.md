# reSpeaker Flex XVF3800 + XIAO ESP32S3：硬體資料

> 這份只放有出處的數字。標「⚠ 待驗證」的，要等實機量到才算數。

## 系統方塊

```
 4-mic array ──PDM──▶ XMOS XVF3800 ──I2S──▶ XIAO ESP32S3 ──USB-Serial/JTAG──▶ PC (COM8)
 (圓形 44mm /        (AEC/BF/NS/AGC/DoA)  ◀─I2S──  (I2S master)
  線性 33mm)              │  ▲                 │
                          │  └──── I2C 0x2C ───┤  (控制指令)
                          ▼                    │
                    TLV320AIC3104 ◀── I2C 0x18 ┘
                    (3.5mm AUX / 喇叭 JST 10W@4Ω)
```

## USB 連接埠

| 埠 | 接到 | VID:PID | 用途 |
|---|---|---|---|
| XIAO 的 USB-C | ESP32S3 | `303A:1001` | ESP32 燒錄 (esptool)、bring-up shell (COM) |
| 核心板 USB-C（靠近 RST 鈕） | XVF3800 | `2886:001A` | USB 韌體時 = UAC2 麥克風；任何韌體都可以 DFU |
| 核心板 PH2.0（有卡榫） | XVF3800 | ⚠ 待驗證 | wiki 說也支援 UAC2 / DFU |

## XIAO ↔ XVF3800 腳位

| 訊號 | ESP32S3 GPIO | 方向 | 出處 |
|---|---|---|---|
| I2C SDA | 5 | ↔ | Seeed GPIO 範例用 `Wire.begin()` 的預設腳 |
| I2C SCL | 6 | → | 同上 |
| I2S BCLK | 8 | ESP32 → | Seeed `reSpeaker_flex_i2s_test.md` |
| I2S WS/LRCLK | 7 | ESP32 → | 同上 |
| I2S DOUT | 44 | ESP32 → XVF | 同上（播放／AEC 參考訊號） |
| I2S DIN | 43 | XVF → ESP32 | 同上（處理後的麥克風音訊） |
| MCLK | — | — | Seeed 範例沒有設定；⚠ 待驗證 |
| XVF reset | ⚠ 未公開 | ESP32 → | wiki 只說「有一根 IO 可以 reset XVF」 |

- I2S 角色：**XVF3800 是 clock master，ESP32 要當 slave**（實測，見 [R003](../logs/R003_i2s_role_xvf_is_master.md)）
  - ESP32 的 I2S 關掉時，WS 上還是量得到 48 kHz
  - ESP32 當 master 會搶時脈，收到 −6 dBFS 的垃圾
  - ⚠ 這跟 Seeed `xmos_firmwares/README.md`（「i2s images are slave」）以及它的 full-duplex 範例（`is_master = true`）都相反。Seeed 的 playback 範例（`is_master = false`）才是對的
- 這塊板子上的 XVF 映像檔：`BLD_MSG = inthost-lr48-sqr-i2c`、`VERSION = 1.0.0` → 48 kHz
- 格式：32-bit slot、立體聲。取樣率由 XVF 決定；內部用 16 kHz 處理，所以 8 kHz 以上幾乎沒有內容

## I2C 控制協定（XVF3800 @ 0x2C）

- 寫入：`[resid][cmdid][len][payload...]`
- 讀取：先寫 `[resid][cmdid|0x80][len+1]`，再讀 `len+1` bytes。第 1 個 byte 是 status：
  - `0` = 成功
  - `64` = 忙碌，要重試
- 指令表：`third_party/reSpeaker_Flex/python_control/xvf_host.py` 的 `PARAMETERS`（共 121 個）。常用的幾個：

| 名稱 | resid | cmd | 型別 × 數量 | 存取 |
|---|---|---|---|---|
| VERSION | 48 | 0 | uint8 × 3 | ro |
| REBOOT | 48 | 7 | uint8 × 1 | wo |
| SAVE_CONFIGURATION | 48 | 9 | uint8 × 1 | wo |
| AIC3104_HP_LEVEL | 48 | 11 | uint8 × 1 (0–9) | rw |
| AUDIO_MGR_OP_L / _R | 35 | 15 / 19 | uint8 × 2 (category, source) | rw |
| I2S_INACTIVE | 35 | 24 | uint8 × 1 | ro |
| GPO_READ_VALUES | 20 | 0 | uint8 × 6 | ro |
| LED_EFFECT | 20 | 12 | uint8 × 1 | rw |
| DOA_VALUE | 20 | 18 | uint16 × 2 (角度, 有沒有人說話) | ro |

## XVF3800 GPIO（Seeed GPIO 頁）

| 腳 | 方向 | 功能 |
|---|---|---|
| X1D09 | in | Boot 鈕 / GPI0 |
| X0D30 | out | SD/FAULT 控制 |
| X0D31 | out | 功放 (PA) 控制 |
| X0D32 / X0D33 | out | XMOS GPIO 1 / 2（FPC 上） |

## XMOS 韌體映像檔（`third_party/reSpeaker_Flex/xmos_firmwares/`，目前最新 v1.0.4）

命名規則：`respeaker_flex_<usb|i2s>_<c|l><16k|48k><2ch|6ch>_v<x.y.z>.bin`

- `c` = 圓形陣列，`l` = 線性陣列
- `6ch` 只有 USB 版：前 2 聲道是處理後的音訊，第 3–6 聲道是 4 支麥克風的原始訊號
- USB 映像檔：用 XVF 的 USB-C 埠，`dfu-util -R -e -a 1 -D <file>`
- I2S 映像檔：出廠預設（帶 XIAO 的版本）

## 出處

- https://wiki.seeedstudio.com/respeaker_flex_introduction/
- https://wiki.seeedstudio.com/respeaker_flex_xiao_introduction/
- https://github.com/Seeed-Studio/wiki-documents（`sites/en/docs/Sensor/reSpeaker_flex/*.md`）
- https://github.com/respeaker/reSpeaker_Flex @ `99a5047`
