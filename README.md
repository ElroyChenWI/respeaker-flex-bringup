# MIC_ARRAY — reSpeaker Flex XVF3800 EVK bring-up

EVK：**Seeed reSpeaker Flex XVF3800 + XIAO ESP32S3**
- 4 支麥克風陣列 → XMOS XVF3800（負責 AEC、beamforming、降噪、AGC、DoA）→ 用 I2S 送到 ESP32S3 → 再經 USB 送到 PC

## 資料夾

```
docs/hardware.md          腳位、I2C 協定、韌體映像檔、USB 埠（都有出處）
docs/bringup_plan.md      B0–B7 關卡，以及每一關的 PASS 條件
logs/R<NNN>_*.md          debug／實驗日誌（hypothesis / 動作 / 觀察 / 結論）
firmware/xiao_esp32s3/    ESP32S3 bring-up shell（PlatformIO + Arduino）
  include/board_pins.h      所有腳位和位址
  src/xvf3800.*             XVF3800 I2C 控制（讀、寫、重試）
  src/i2s_link.*            I2S full-duplex（ESP32 = master）
  src/main.cpp              文字指令 shell：info / i2cscan / ver / doa / xr / xw / i2s / stat / rec / tone
host/                     PC 端 Python 工具
  env_check.py              B0：看裝置和工具在不在
  evk_cli.py                指令列工具：用名稱讀寫 XVF 參數、看 DoA、smoke test
  record_wav.py             透過 COM 錄音存成 WAV，順便報 dBFS
  evk/                      serial_link（shell 協定）、xvf_table（指令表）
scripts/                  pio.ps1、backup_xiao_flash.ps1、fetch_vendor.ps1
third_party/              Seeed 原廠 repo（不進 git，用 fetch_vendor.ps1 下載）
captures/                 錄音和備份（只有 R0XX 證據檔會進 git）
```

## 快速開始（PowerShell，在 repo 根目錄執行）

```powershell
.\scripts\fetch_vendor.ps1                        # 下載 Seeed repo（XMOS 韌體 + 指令表）
py -3.11 -m pip install -r host\requirements.txt
py -3.11 host\env_check.py                        # B0
.\scripts\backup_xiao_flash.ps1 -Port COM8        # B0.5：燒錄前先備份出廠 flash
.\scripts\pio.ps1 run -t upload --upload-port COM8   # B1
py -3.11 host\evk_cli.py smoke                    # B1–B3
py -3.11 host\record_wav.py --sec 5               # B4
```

Shell 也可以手動玩：`.\scripts\pio.ps1 device monitor -p COM8`，然後輸入 `help`。

## 現況

| 關卡 | 狀態 | 日誌 |
|---|---|---|
| B0 環境 | ✅ PASS | [R001](logs/R001_evk_usb_baseline.md) |
| B0.5 備份 | ⏳ 還沒做 | |
| B1–B7 | ⏳ 韌體已經寫好、編譯過，還沒上板 | |
