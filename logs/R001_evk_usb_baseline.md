# R001 — EVK USB 連線 baseline（動任何東西之前）

- 日期：2026-10-10
- 板子：reSpeaker Flex XVF3800 + XIAO ESP32S3（出廠狀態，還沒燒過任何東西）
- 關卡：B0

## Hypothesis

把 XIAO 的 USB-C 接到 PC，應該會出現 ESP32S3 的 USB-Serial/JTAG。XVF3800 跑出廠的 I2S 映像檔，所以 Windows 不會出現 UAC 麥克風。

## 動作

1. 接上 XIAO USB-C 之前和之後，各跑一次 `Get-PnpDevice -PresentOnly` 列出裝置
2. 用 pyserial 被動讀 COM8 十秒：`dtr=False`、`rts=False`、不送任何東西
3. 跑 `host/env_check.py`

## 觀察

- 新出現 `USB\VID_303A&PID_1001`（USB 序列裝置 COM8 + USB JTAG/serial debug unit），MAC `68:EE:8F:46:45:B0`
- 沒有 `2886:*`，也沒有新的音訊端點 → XVF3800 沒有用 USB 音訊裝置的身分出現
- 很久以前接過的 `IFX-AUDIOHUB2D`（`058B:0240`，Infineon）沒有出現。那是別的板子，跟這次無關
- **COM8 上出廠韌體一直主動送二進位資料**，大約 **38.9 KB/s**（10.04 秒收到 390090 bytes）
  - 把資料當 int16 或 int32 解讀（試了各種位移），相鄰 sample 的差值 / 標準差都 ≈ 1.25–1.32，不像平滑的 PCM，比較像雜訊或壓縮過的資料
  - 前 64 bytes：`cf4deb39dd2b91e70f58723070a07ce07ed8f0a01048c2083d30a5307cc812c8...`
  - 證據檔：`captures/R001_com8_factory_10s.bin`（sha256 `a341ccb090eb6f6eb2d1ad1800b5e6cdb6bcc686ffb0431ab8660f58c3f35d29`）
- `env_check.py`：B0 PASS。pio 和 esptool 都在。dfu-util 沒有（B7 才會用到）

## 結論

- B0 **PASS**。PC ↔ XIAO 的連線正常
- 出廠的 ESP32 韌體會自己往外送資料，格式還不知道（不是單純的 PCM）。**燒我們的 shell 之前，要先跑 B0.5 備份整顆 flash**，之後才能刷回去做對照
- 下一步：B0.5 備份，然後 B1 燒錄 bring-up shell
