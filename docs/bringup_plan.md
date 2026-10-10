# Bring-up 計畫（一關一關過）

規則：
- 一次只過一關，前一關 PASS 才往下走
- 每一關都開一個 R0XX 日誌（`logs/R<NNN>_<slug>.md`）
- 失敗就 revert，不留半套

| 關卡 | 目標 | 怎麼測 | PASS 條件 |
|---|---|---|---|
| **B0** 環境 | PC 看得到板子、工具都在 | `py -3.11 host\env_check.py` | 看到 `303A:1001`，pio / esptool 都 OK |
| **B0.5** 備份 | 保住出廠 ESP32 韌體 | `.\scripts\backup_xiao_flash.ps1 -Port COM8` | 得到 8 MB `.bin` 和 sha256 |
| **B1** 燒 shell | ESP32 跑我們的韌體 | `.\scripts\pio.ps1 run -t upload --upload-port COM8`，再跑 `evk_cli.py raw info` | 回應 `OK info` |
| **B2** I2C | ESP32 可以控制 XVF3800 | `evk_cli.py raw i2cscan`、`evk_cli.py get VERSION` | 掃到 0x2C（和 0x18），VERSION 有值 |
| **B3** I2S 收音 | 收到 XVF 送出的處理後音訊 | `evk_cli.py raw "i2s start"`、`evk_cli.py raw "stat 1000"`、`evk_cli.py get I2S_INACTIVE` | `nonzero` 超過 50%；安靜時和拍手時的 rms 差 ≥ 20 dB；`I2S_INACTIVE = 0` |
| **B4** 錄音落地 | 錄成 WAV，可以聽 | `py -3.11 host\record_wav.py --sec 5` | 檔案能播放，`padded=0` |
| **B5** 播放 / AEC 參考 | ESP32 → XVF → AIC3104 有聲音 | `evk_cli.py raw "tone 1000 2000 -20"`，用耳機接 AUX | 聽得到 1 kHz |
| **B6** DSP 功能 | DoA、LED、增益 | `evk_cli.py doa --watch`、`evk_cli.py set LED_EFFECT 4` | 繞著板子講話，角度跟著變 |
| **B7**（選配）USB 模式 | XVF 直接當 PC 麥克風 | 先備份目前的 XVF 映像檔版本，再 DFU 刷 `usb_*` 映像檔 | Windows 出現 UAC2 麥克風；6ch 版可以拿到 4 支麥克風的原始訊號 |

`py -3.11 host\evk_cli.py smoke` 一次跑完 B1–B3。

## 已知風險

- **I2S master/slave**：Seeed 的範例互相矛盾，B3 不過的話，先懷疑這個。
- **取樣率**：XVF 映像檔是 16k 還是 48k，B2 讀 `BLD_MSG` 可以知道。ESP32 的 `i2s start <rate>` 要跟它一致。
- **串口頻寬**：16k × 2ch × 16bit = 64 KB/s，沒問題。48k × 32bit = 384 KB/s，USB-Serial/JTAG 可能會掉資料（看 `padded`）。
- **GPIO43** 同時是 UART0 TX，開機時 ROM 會在上面輸出 log。韌體已經關掉 core log，但 ROM 那段關不掉。
