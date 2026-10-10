# reSpeaker Flex XVF3800 EVK — Bring-up Toolkit

讓 **Seeed reSpeaker Flex XVF3800 + XIAO ESP32S3** 這套 EVK 可以在 PC 上**收音、錄音、看 DSP 狀態、控制 beamforming**。

裡面有：ESP32S3 韌體、PC 端 Python 工具，以及一個網頁 GUI。

![EVK GUI](docs/img/gui.png)

> **先講最重要的一件事：這塊板子上，XVF3800 才是 I2S 的 clock master，ESP32 必須當 slave。**
> Seeed 的文件和部分範例寫成相反（ESP32 當 master），照著做只會收到滿幅度的雜訊。
> 本專案已經實測並修正，細節見 [logs/R003](logs/R003_i2s_role_xvf_is_master.md)。

---

## 目錄

- [系統架構](#系統架構)
- [目前能做什麼](#目前能做什麼)
- [需要準備的東西](#需要準備的東西)
- [快速開始（第一次使用）](#快速開始第一次使用)
- [GUI 使用說明](#gui-使用說明)
- [命令列工具](#命令列工具)
- [ESP32 韌體的指令介面](#esp32-韌體的指令介面)
- [專案結構](#專案結構)
- [疑難排解](#疑難排解)
- [Bring-up 進度與下一步](#bring-up-進度與下一步)
- [參考資料](#參考資料)

---

## 系統架構

```
                          reSpeaker Flex 核心板
 ┌──────────────┐   PDM   ┌──────────────────────┐   I2S (XVF = master, 48 kHz)   ┌───────────────┐   USB-C    ┌──────────┐
 │ 4-mic array  │ ──────▶ │ XMOS XVF3800         │ ─────────────────────────────▶ │ XIAO ESP32S3  │ ─────────▶ │    PC    │
 │ (FPC 24-pin) │         │ AEC / Beamforming /  │ ◀── I2S (播放 / AEC 參考) ──── │ (I2S slave)   │  序列埠    │ Python + │
 └──────────────┘         │ NS / AGC / VAD / DoA │ ◀── I2C 0x2C (參數控制) ────── │ 本專案韌體     │            │ 網頁 GUI │
                          └──────────┬───────────┘                                 └───────────────┘            └──────────┘
                                     │ I2C 0x18
                              TLV320AIC3104 codec ──▶ 3.5 mm AUX / 喇叭
```

- **XVF3800**：負責所有語音 DSP，處理完的立體聲用 I2S 送出去
- **ESP32S3**：當中間人。用 I2S 收音、用 I2C 控制 XVF，再透過 USB 序列埠跟 PC 講話
- **PC**：用 Python 工具或網頁 GUI 操作；錄音存成 WAV

---

## 目前能做什麼

| 功能 | 狀態 |
|---|---|
| PC 錄到 XVF 處理後的聲音（48 kHz、立體聲、16/32-bit WAV） | ✅ 已驗證，不掉資料 |
| 讀寫 XVF3800 的 121 個參數（I2C） | ✅ |
| 即時看 DSP 狀態：AGC、beam 方向、人聲偵測、DoA、運算餘裕 | ✅ |
| 手動控制 beamforming（固定 beam、切換輸出路由） | ✅ |
| 網頁 GUI | ✅ |
| Beamforming 指向性的數據（dB） | ⏳ 測試程式寫好了（`beam_test.py`），還沒正式量 |
| AEC 回音消除（要播放參考訊號） | ⏳ 還沒做 |
| 脫離 PC 運作（Wi-Fi 串流） | ❌ 還沒做 |

---

## 需要準備的東西

### 硬體

- **reSpeaker Flex XVF3800**（圓形或線性陣列），帶 **XIAO ESP32S3** 的版本（SKU `-C4-1` / `-L4-1`）
- 一條 USB-C 傳輸線（不能是只能充電的線）

**USB 要插 XIAO 上的 USB-C**，不是核心板上那個。插上後，Windows 會出現一個 `USB 序列裝置 (COMx)`，VID:PID 是 `303A:1001`。

| 埠 | 接到 | 用途 |
|---|---|---|
| **XIAO 的 USB-C** | ESP32S3 | ✅ 本專案用這個：燒錄、收音、控制 |
| 核心板的 USB-C（靠近 RST 鈕） | XVF3800 | 只有刷 XVF 韌體（DFU）或用 USB 韌體時才會用到 |

### 軟體

| 工具 | 版本 | 安裝 |
|---|---|---|
| Windows | 10 / 11 | `scripts/*.ps1` 是 PowerShell；Python 工具在其他平台也能用 |
| Git | 任意版本 | https://git-scm.com |
| Python | 3.10 以上（開發時用 3.11） | https://www.python.org |
| PlatformIO | Core 6.x | 裝 VS Code 的 PlatformIO 擴充套件，或執行 `pip install platformio` |

> PlatformIO 第一次編譯時會自動下載 ESP32 工具鏈和 esptool，大約幾百 MB。

---

## 快速開始（第一次使用）

以下指令都在 **repo 根目錄**、用 **PowerShell** 執行。

> 如果電腦裝了好幾個 Python，下面的 `python` 改成 `py -3.11`。

### 1. Clone，並下載 Seeed 原廠檔案

```powershell
git clone <this-repo-url> MIC_ARRAY
cd MIC_ARRAY
.\scripts\fetch_vendor.ps1
```

`fetch_vendor.ps1` 會把 [respeaker/reSpeaker_Flex](https://github.com/respeaker/reSpeaker_Flex) 抓到 `third_party/`，並鎖在固定版本。

它提供兩樣東西：
- XVF3800 的指令表（host 工具需要）
- XMOS 韌體檔（之後要刷 XVF 才用得到）

### 2. 安裝 Python 套件

```powershell
python -m pip install -r host\requirements.txt
```

### 3. 確認電腦看得到板子（B0）

```powershell
python host\env_check.py
```

最後一行要看到 `B0 PASS`。如果是 FAIL，代表沒找到 `303A:1001`：換一條 USB 線，或換一個 USB 孔。

### 4.（建議）備份 ESP32 原本的韌體

```powershell
.\scripts\backup_xiao_flash.ps1
```

- 只讀不寫，把整顆 8 MB flash 存到 `captures/`
- 大約要 12 分鐘
- 之後想回到原狀：`.\scripts\restore_xiao_flash.ps1 captures\xiao_flash_backup_<時間>.bin`

### 5. 編譯並燒錄 ESP32 韌體（B1）

```powershell
.\scripts\pio.ps1 run -t upload
```

PlatformIO 會自動找到 COM port。看到 `[SUCCESS]` 就完成了。

### 6. 一鍵自我檢查（B1–B3）

```powershell
python host\evk_cli.py smoke
```

應該看到：

```
[PASS] B1 shell: OK info i2s=off rate=0 role=slave
[PASS] B2 i2c scan: # 0x18 aic3104 | # 0x2C xvf3800 | OK i2cscan found=2
[PASS] B2 xvf version: OK ver 1.0.0
[PASS] B3 xvf drives clocks: OK clkprobe ... ws_hz~48000 ...
[PASS] B3 i2s start (slave): OK i2s started rate=48000 role=slave
[PASS] B3 i2s level: OK stat frames=48000 L_rms_dbfs=-58.4 ...
SMOKE PASS
```

### 7. 開 GUI，開始錄音

```powershell
python host\evk_gui.py
```

用瀏覽器打開 **http://127.0.0.1:8765**。按「● 錄音」，錄好的檔案可以直接在頁面上播放。

也可以不開 GUI，直接用命令列錄：

```powershell
python host\record_wav.py --sec 5
```

---

## GUI 使用說明

啟動：`python host\evk_gui.py`（選項：`--port COM8`、`--http 8765`）

| 區塊 | 功能 |
|---|---|
| **音量** | L/R 即時音量（dBFS），細線是峰值；下面是最近 20 秒的走勢 |
| **方向** | 4 支麥克風的位置，以及幾條方向線：<br>藍 = 自動選擇的 beam<br>灰虛線 = 自由掃描的 beam<br>紫 = 固定 beam<br>綠 = 有人說話時的 DoA（標題旁的小燈也會亮）<br>座標：0° 朝右（+x），逆時針為正 |
| **DSP 狀態** | AGC 增益、AEC 有沒有收斂、AEC 和 PP thread 的運算餘裕（越大越好，0 代表過載）、各 beam 的語音能量 |
| **錄音** | 設定秒數和位元數，按「● 錄音」。錄完自動播放並畫出波形；下面列出最近的錄音 |
| **Beamforming 控制** | 三個輸出路由的快速切換：預設、原始麥克風、固定 beam 送到 L/R。拖拉桿可以把 beam 1 轉到任意角度，beam 2 會自動放在反方向 |
| **XVF3800 參數** | 121 個參數，可以搜尋、讀取、寫入。會重開機或改寫 flash 的參數，寫入前會先確認 |

**體驗 beamforming：**
1. 按「固定 beam → L/R」
2. 從某個方向講話
3. 拖 beam 1 對準你，L（對準你）的音量應該比 R（背對你）高

> GUI 裡改的設定都是**暫時的**，XVF 重開機就恢復。只有在參數表寫入 `SAVE_CONFIGURATION`，才會存進 XVF 的 flash。

---

## 命令列工具

所有工具都會自動找 XIAO 的 COM port。要手動指定的話，用 `--port COM8`，或設定環境變數 `EVK_PORT=COM8`。

> ⚠️ COM port 同一時間只能被一個程式打開。開著 GUI 時，其他工具會連不上。

### `host/evk_cli.py`：萬用指令列

```powershell
python host\evk_cli.py smoke                    # B1–B3 自我檢查
python host\evk_cli.py raw "info"               # 直接送一行 shell 指令
python host\evk_cli.py list AGC                 # 列出名稱含 AGC 的 XVF 參數
python host\evk_cli.py get VERSION              # 用名稱讀參數
python host\evk_cli.py get AEC_AZIMUTH_VALUES
python host\evk_cli.py set LED_EFFECT 3         # 用名稱寫參數（暫時，不存檔）
python host\evk_cli.py doa --watch              # 持續顯示聲源方向
python host\evk_cli.py dsp --watch              # 持續顯示 DSP 健康狀態
```

### `host/record_wav.py`：錄音

```powershell
python host\record_wav.py --sec 10                         # 存到 captures\rec_<時間>.wav
python host\record_wav.py --sec 5 --bits 32 -o test.wav    # 32-bit 原始精度
```

錄完會印出每個聲道的 RMS 和峰值（dBFS）。`padded=0` 代表一筆都沒掉。

### `host/beam_test.py`：Beamforming 指向性 A/B

```powershell
python host\beam_test.py
```

從同一個位置一直講話，大約 20 秒。程式會：
1. 找出你的方向
2. 把 beam 對準你、再背對你，各錄一次
3. 兩個 beam 對調再錄一次，用來抵消左右聲道本身的音量差

最後印出「對準 vs 背對」差幾 dB。測完自動改回原設定。

### `host/env_check.py`：環境檢查

列出所有 COM port、已知的 USB 裝置，以及 pio、esptool、dfu-util 這幾個工具在不在。

### `scripts/`

| 腳本 | 用途 |
|---|---|
| `pio.ps1 <args>` | 在韌體資料夾裡執行 PlatformIO。不管 pio 有沒有在 PATH 上都能用 |
| `fetch_vendor.ps1` | 下載 Seeed reSpeaker_Flex repo（鎖定版本） |
| `backup_xiao_flash.ps1` | 備份 XIAO 整顆 flash（只讀） |
| `restore_xiao_flash.ps1 <img>` | 把備份寫回 XIAO |

---

## ESP32 韌體的指令介面

韌體在 `firmware/xiao_esp32s3/`，用 PlatformIO + Arduino（arduino-esp32 2.0.17）開發。

它透過 USB 序列埠提供一行一行的文字指令。你可以直接打：`.\scripts\pio.ps1 device monitor`，然後輸入 `help`。

**規則：** 每個指令最後一定回一行 `OK ...` 或 `ERR ...`。以 `#` 開頭的行是附加資訊。

| 指令 | 說明 |
|---|---|
| `help` | 列出指令 |
| `info` | 韌體版本、晶片資訊、腳位、I2S 狀態 |
| `i2cscan` | 掃 I2C bus（應該看到 0x18 和 0x2C） |
| `ver` | XVF3800 韌體版本 |
| `doa` | 聲源方向和人聲偵測 |
| `xr <resid> <cmd> <n>` | XVF 原始讀取，讀 n 個 bytes |
| `xw <resid> <cmd> <bytes...>` | XVF 原始寫入 |
| `i2s start [rate] [master\|slave]` / `i2s stop` | 啟動或停止 I2S。預設 `48000 slave` |
| `clkprobe` | I2S 關掉時，量 BCLK/WS 上有沒有外部時脈（用來判斷誰是 master） |
| `stat [ms]` | 收一段音訊，回報 L/R 的 RMS、峰值、非零 sample 數 |
| `rec <ms> [16\|32]` | 錄音，用二進位串流送出（見下方） |
| `tone <hz> <ms> [dbfs]` | 送正弦波到 XVF 的 I2S 輸入（播放路徑，還沒驗證） |

**`rec` 的資料格式：**

```
REC rate=48000 ch=2 bits=16 bytes=<N>\n
<N bytes：little-endian PCM，L/R 交錯>
\nOK rec frames=<F> padded=<P>\n        ← P > 0 代表有資料不夠、補了零
```

**腳位**（`firmware/xiao_esp32s3/include/board_pins.h`）：

| 訊號 | GPIO |
|---|---|
| I2C SDA / SCL | 5 / 6 |
| I2S BCLK / WS | 8 / 7 |
| I2S DOUT（ESP32 → XVF）/ DIN（XVF → ESP32） | 44 / 43 |

完整的硬體資料、I2C 協定、XMOS 韌體檔清單，見 [docs/hardware.md](docs/hardware.md)。

---

## 專案結構

```
.
├── README.md
├── docs/
│   ├── hardware.md            腳位、I2C 協定、USB 埠、XMOS 韌體檔（都有出處）
│   ├── bringup_plan.md        B0–B7 關卡和每一關的 PASS 條件
│   └── img/gui.png
├── firmware/xiao_esp32s3/     ESP32S3 韌體（PlatformIO）
│   ├── platformio.ini
│   ├── include/board_pins.h   所有腳位、位址、I2S 預設值
│   └── src/
│       ├── main.cpp           文字指令 shell
│       ├── xvf3800.{h,cpp}    XVF3800 I2C 控制（含忙碌重試）
│       └── i2s_link.{h,cpp}   I2S full-duplex（master/slave 可選）
├── host/                      PC 端 Python
│   ├── evk_gui.py + gui/      網頁 GUI（只用 Python 內建套件）
│   ├── evk_cli.py             指令列工具
│   ├── record_wav.py          錄音
│   ├── beam_test.py           beamforming A/B
│   ├── env_check.py           環境檢查
│   ├── requirements.txt
│   └── evk/
│       ├── serial_link.py     shell 協定、自動找 COM port
│       └── xvf_table.py       XVF 指令表（從 Seeed 的 xvf_host.py 解析）
├── scripts/                   PowerShell 腳本（燒錄、備份、還原、下載原廠檔）
├── logs/R0XX_*.md             實驗與 debug 日誌（hypothesis / 動作 / 觀察 / 結論）
├── captures/                  錄音和備份（只存在本機，不進 git）
└── third_party/               Seeed 原廠 repo（不進 git，用 fetch_vendor.ps1 下載）
```

---

## 疑難排解

| 症狀 | 原因 / 解法 |
|---|---|
| `env_check` 找不到 `303A:1001` | 插到核心板的 USB-C 了，要插 **XIAO** 的；或是用到只能充電的線 |
| 錄到的聲音是滿幅度雜訊（RMS 約 −6 dBFS） | ESP32 被設成 I2S master，跟 XVF 搶時脈。韌體預設是 slave；如果改過，用 `i2s start 48000 slave` |
| `stat` 回 `no samples` | XVF 沒送時脈。先跑 `clkprobe`，看 `ws_hz` 是不是 48000；不是的話，按核心板的 RST 重開 XVF |
| `could not open port` / `Access denied` | COM port 被別的程式佔用：GUI、serial monitor、Arduino IDE。先關掉它們 |
| `smoke` 的 B2 失敗（找不到 0x2C） | XVF 還在開機，或 I2C 沒接好。等幾秒再試，或按 RST |
| 取樣率不對、聲音變快或變慢 | slave 模式下取樣率由 XVF 決定。這塊板子的 XVF 韌體是 `inthost-lr48`，所以是 48 kHz。如果 XVF 刷成 16k 韌體，錄音時要加 `--rate 16000` |
| `third_party/... missing` | 還沒跑 `.\scripts\fetch_vendor.ps1` |
| 備份 flash 很慢 | 正常。USB-Serial/JTAG 讀 8 MB 大約要 12 分鐘 |
| 想回到買來時的 ESP32 韌體 | 用第 4 步的備份：`.\scripts\restore_xiao_flash.ps1 <備份檔>` |

---

## Bring-up 進度與下一步

詳細的關卡和 PASS 條件見 [docs/bringup_plan.md](docs/bringup_plan.md)，每一關的過程記在 `logs/`。

| 關卡 | 狀態 | 日誌 |
|---|---|---|
| B0 環境 | ✅ | [R001](logs/R001_evk_usb_baseline.md) |
| B0.5 備份 flash | ✅ | [R002](logs/R002_xiao_flash_backup.md) |
| B1 shell / B2 I2C / B3 I2S | ✅ XVF = I2S master，ESP32 = slave，48 kHz | [R003](logs/R003_i2s_role_xvf_is_master.md) |
| B4 錄成 WAV | ✅ 確認錄得到人聲 | [R003](logs/R003_i2s_role_xvf_is_master.md) |
| XVF DSP 健康 | ✅ 有在跑（AEC 還沒驗證） | [R004](logs/R004_xvf_dsp_health.md) |
| B5 播放 + AEC | ⏳ 要接耳機或喇叭到 AUX | |
| B6 DoA 準確度 / beam 指向性數據 | ⏳ `beam_test.py` 寫好了 | |
| B7 USB 模式（XVF 直接當 PC 麥克風，6ch 原始麥克風） | ⏳ 選配，會刷 XVF 韌體 | |

---

## 參考資料

- Seeed Wiki：[reSpeaker Flex](https://wiki.seeedstudio.com/respeaker_flex_introduction/)、[reSpeaker Flex with XIAO ESP32S3](https://wiki.seeedstudio.com/respeaker_flex_xiao_introduction/)
- 原廠 repo：[respeaker/reSpeaker_Flex](https://github.com/respeaker/reSpeaker_Flex)（XMOS 韌體、`xvf_host.py`）
- Wiki 原始碼：[Seeed-Studio/wiki-documents](https://github.com/Seeed-Studio/wiki-documents)（`sites/en/docs/Sensor/reSpeaker_flex/`）
- XMOS：[XVF3800 Host application / Output selection](https://www.xmos.com/documentation/XM-014888-PC/html/modules/fwk_xvf/doc/user_guide/03_using_the_host_application.html#output-selection)
