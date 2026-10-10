# XVF3800 麥克風陣列研發：從黑盒子到自己的 Beamformer

[English](README.md) | **繁體中文**

**從外部量測解析商用語音 DSP，從頭重建它的訊號處理鏈，並在同樣的條件下比較兩者。**

| 問題 | 答案與證據 |
|---|---|
| 封閉的商用語音 DSP，沒有原始碼也能理解嗎？ | 可以到一定程度：時脈角色、座標系統和處理管線結構，全部從介面量測推出來（見「黑箱特性分析」） |
| 只用原始麥克風，能重現它的定位嗎？ | 自己的 SRP-PHAT 跟晶片**中位數差 2°**（[R006](logs/R006_srp_phat_doa_vs_xvf.md)） |
| 這個陣列用哪種 beamforming 最好？ | 實作 4 種並公平比較，**MVDR + Wiener（MWF）**：SNR **+11.4 dB**、STOI **0.72 → 0.80**（[R009](logs/R009_fair_eval_shadow_filtering.md)） |
| 怎麼確定數字是誠實的？ | 訓練和評分用不同時段、數位混合 + shadow filtering，並證明簡單的 SNR 指標可以被操控（[R008](logs/R008_mwf_postfilter_and_metric_limits.md)） |
| 要拿到原始麥克風訊號，做了什麼？ | 自己實作 XMOS 的 I2C DFU 協定：板子沒有 SafeMode 鈕，預設韌體也沒有開 USB（[R005](logs/R005_xvf_usb6ch_via_i2c_dfu.md)） |

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
- [自己的陣列演算法 vs XVF3800](#自己的陣列演算法-vs-xvf3800)
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
 │ (FPC 24-pin) │         │ AEC / Beamforming /  │ ◀── I2S (播放) ────────────── │ (I2S slave)   │  序列埠    │ Python + │
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
| PC 錄到 XVF 處理後的聲音（48 kHz、立體聲、16/32-bit WAV；I2S 韌體，經 ESP32） | ✅ Verified：串流不掉資料（`padded=0`） |
| 4 支麥克風原始訊號 + 2 聲道處理後輸出（16 kHz；USB 6ch 韌體，直接進 PC） | ✅ Verified |
| 讀寫 XVF3800 全部 121 個參數（I2C 經 ESP32，或 USB） | ✅ Verified |
| 用 I2C 更新 XVF3800 韌體（不需要 SafeMode 鈕、不需要 USB） | ✅ Verified |
| 即時 DSP 監看：VAD、DoA、beam 方向、運算餘裕 | ✅ Verified |
| XVF beam 控制：自動選擇、自由掃描、固定 beam、輸出路由 | ✅ Verified：GUI 可以即時操控 |
| 自己寫的 SRP-PHAT DoA | ✅ Verified：跟 XVF 中位數差 2° |
| 自己寫的 beamformer：delay-and-sum、MVDR、MVDR + Wiener（MWF） | ✅ Verified：MWF SNR +11.4 dB、STOI 0.72 → 0.80（離線） |
| 網頁 GUI | ✅ Verified |
| 即時運算、RTF 轉向向量、用喇叭跟 XVF 做 A/B | 🗺️ Roadmap |

> **Verified** = 在實機上量過，數據和方法都記在 `logs/`。

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

## 自己的陣列演算法 vs XVF3800

把 XVF3800 換成 USB 6ch 韌體後，第 3–6 聲道就是 4 支麥克風的原始訊號（沒有增益、沒有延遲）。以下所有演算法都在 [`host/algo`](host/algo) 用 NumPy 從頭寫，並跟 XMOS 晶片處理同一段錄音的結果比較。

### 1. XVF3800 黑箱特性分析

XVF 的 DSP 是封閉的，所以只從**介面上的量測**推測它的行為，沒有動到韌體：

| 量測 | 發現 |
|---|---|
| 關掉 ESP32 的 I2S，計算時脈邊緣 | XVF3800 是 **I2S clock master**，48 kHz（Seeed 文件寫 slave） |
| `DOA_VALUE`、自動選擇 beam 方位、`AEC_MIC_ARRAY_GEO` 三者比對 | 用同一套座標：邊長 44.4 mm 的正方形，0° = +x，逆時針為正 |
| 從 DSP 管線不同位置取訊號（原始麥克風 → beam → 後處理） | 只有 beam：比單麥 **+1.3 dB**；完整處理：**+14.8 dB** → 大部分效果來自 beam **之後**的後處理 |
| 自己的 SRP-PHAT vs `DOA_VALUE` | 中位數差 **2°** → XVF 的定位行為跟 PHAT 類的方法一致 |

根據這些量測推測的架構是：**beamformer → 頻譜後處理 → 增益控制**，也就是經典的語音前端結構。自己的實作照同樣的結構，好讓每一級都能單獨量測。

### 2. 聲源定位：SRP-PHAT

6 組麥克風配對、PHAT 加權、1° 網格、300–3800 Hz（這個陣列 3.86 kHz 以上會有空間混疊）。

| | 結果 |
|---|---|
| 合成平面波，24 個方向 | SNR 20 dB 時最大誤差 1°，0 dB 時 4° |
| 真人講話，板子周圍 4 個位置 | 跟 XVF **中位數差 2°**，84% 的幀在 10° 以內 |

合成測試在接硬體之前就抓到一個符號錯誤（每個方向都剛好錯 180°），見 [R006](logs/R006_srp_phat_doa_vs_xvf.md)。

### 3. Beamforming：4 種方法，一套公平的評估

講話和干擾（音樂）在固定位置**分開錄**，再在數位端相加（聲音在空氣中是線性疊加）。每種方法只在混合訊號上決定權重和增益，再把**同一組**權重和增益分別套到講話和噪音上（shadow filtering），得到真正的輸出 SNR、講話失真和清晰度。估計噪音統計的時段和評分的時段是分開的。

| 方法 | SNR 提升 | 講話 SDR | STOI |
|---|---:|---:|---:|
| 單支麥克風 | 0 dB | — | 0.723 |
| 單支麥克風 + Wiener | +7.5 dB | 11.2 dB | 0.741 |
| Delay-and-sum | +0.3 dB | — | 0.740 |
| MVDR | +4.0 dB | 7.9 dB | 0.785 |
| **MVDR + Wiener（MWF）** | **+11.4 dB** | 7.1 dB | **0.797** |

*輸入 SNR +6.7 dB。輸入 SNR 0 dB 時，MWF 提升 +13.7 dB，STOI 從 0.56 提升到 0.69。* 完整方法和限制見 [R009](logs/R009_fair_eval_shadow_filtering.md)。

**數據說明了什麼：**
- **4 種方法裡 MWF 最好**，SNR 和清晰度都是最高
- **清晰度主要來自空間濾波**：只用 Wiener 時 SNR +7.5 dB，STOI 幾乎沒變；MVDR 只有 +4 dB，STOI 卻提升最多
- **能量 SNR 可以被操控**：改用這套評估之前，舊的 SNR 指標幾乎 1:1 跟著 Wiener 的增益下限跑（改一個參數就能從 +11 變成 +29 dB），所以換掉了，見 [R008](logs/R008_mwf_postfilter_and_metric_limits.md)
- **已知的限制**：MVDR 用的是自由場轉向向量，跟有回音的房間不完全吻合，會犧牲一些講話品質（SDR 7.9 dB）。下一步會改用 relative transfer function（RTF）
- XVF3800 是黑盒子，**沒辦法 shadow filtering**，所以不在這張表裡；用喇叭跟 XVF 做 A/B 在 roadmap 上

**空間濾波這一級的初步觀察**：同一段實際錄音（[R007](logs/R007_beamformer_vs_xvf.md)）中，自己的 MVDR 比單支麥克風提升 **+5.4 dB**，XVF3800 的 beam 輸出（ASR beam）只提升 **+1.3 dB**。

這只是初步觀察，還不是定論：
- 只有一次錄音，用的是能量 SNR 指標
- 自己的 MVDR 事先從一段「只有噪音」的錄音學過噪音，XVF 沒有這個優勢
- XVF 的 beam 輸出本身可能還包含其他處理

XVF 的完整處理還多了後處理（同一個指標下 +14.8 dB）。我們對應的那一級是 MWF，目前只做到離線版本。

```powershell
cd host; python -m algo.test_algo; cd ..                   # 合成測試
python host\doa_live.py --sec 10 --label 1                 # 自己 vs XVF 的 DoA，存 6ch WAV + CSV
python host\doa_eval.py                                    # 整理有標籤的 DoA 錄音
python host\mix_eval.py <speech.wav> <noise.wav> [--snr 0] # 公平的 beamformer 比較
```

### XVF3800 的兩種韌體

XVF3800 可以跑兩種映像檔，透過 ESP32 用 I2C 切換（不需要 SafeMode 鈕，也不需要接 XVF 的 USB）：

| 映像檔 | 音訊路徑 | 用途 |
|---|---|---|
| I2S 48 kHz（`i2s/respeaker_flex_i2s_c48k2ch_*.bin`） | 處理後的立體聲 → ESP32 → PC | GUI 錄音、ESP32 整合 |
| USB 6ch 16 kHz（`usb/v1.0.4/respeaker_flex_usb_c16k6ch_v1.0.4.bin`） | 2 聲道處理後 + 4 支原始麥克風 → 直接進 PC（核心板的 USB-C） | 自己的演算法（`host/algo`） |

```powershell
python host\xvf_i2c_dfu.py --status
python host\xvf_i2c_dfu.py third_party\reSpeaker_Flex\xmos_firmwares\usb\v1.0.4\respeaker_flex_usb_c16k6ch_v1.0.4.bin
python host\xvf_i2c_dfu.py third_party\reSpeaker_Flex\xmos_firmwares\i2s\v1.0.4\respeaker_flex_i2s_c48k2ch_v1.0.4.bin
```

只會寫入升級區；出廠映像檔不能被覆寫，升級映像檔無效時 bootloader 會退回出廠映像檔。

---

## 快速開始（第一次使用）

以下指令都在 **repo 根目錄**、用 **PowerShell** 執行。

> 如果電腦裝了好幾個 Python，下面的 `python` 改成 `py -3.11`。

### 1. Clone，並下載 Seeed 原廠檔案

```powershell
git clone https://github.com/ElroyChenWI/respeaker-flex-bringup.git
cd respeaker-flex-bringup
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
| **DSP 狀態** | DSP thread 的運算餘裕（越大越好，0 代表過載）、增益和收斂旗標、各 beam 的語音能量 |
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
python host\evk_cli.py list DOA                 # 列出名稱含 DOA 的 XVF 參數
python host\evk_cli.py get VERSION              # 用名稱讀參數
python host\evk_cli.py get DOA_VALUE
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
│   ├── algo/                  自己的陣列演算法：幾何、SRP-PHAT、DAS / MVDR / Wiener、合成測試
│   ├── doa_live.py / doa_eval.py / mix_eval.py   演算法的錄音與評估
│   ├── xvf_i2c_dfu.py         用 I2C 更新 XVF 韌體
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
| XVF DSP 健康 | ✅ 沒有 bypass、運算有餘裕、beam / VAD / DoA 都有反應 | [R004](logs/R004_xvf_dsp_health.md) |
| B7 用自己的 I2C DFU 刷 USB 6ch 韌體 | ✅ 拿到 4 支麥克風原始訊號；修好序列埠接收緩衝區後，0 次重送 | [R005](logs/R005_xvf_usb6ch_via_i2c_dfu.md) |
| A1 自己的 SRP-PHAT DoA vs XVF | ✅ 中位數差 2° | [R006](logs/R006_srp_phat_doa_vs_xvf.md) |
| A2 真實房間的 beamformer | ✅ MVDR +4.9 dB；XVF 只有 beam +1.3 dB，完整處理 +14.8 dB | [R007](logs/R007_beamformer_vs_xvf.md) |
| A3 Wiener 後處理 + 檢查指標 | ✅ 證明簡單的 SNR 指標可以被操控 | [R008](logs/R008_mwf_postfilter_and_metric_limits.md) |
| A4 公平評估（shadow filtering） | ✅ MWF 最佳：+11.4 dB、STOI 0.72 → 0.80 | [R009](logs/R009_fair_eval_shadow_filtering.md) |
| 下一步 | ⏭️ 即時運算 + 線上估計噪音、RTF 轉向向量、用喇叭跟 XVF 做 A/B | |

---

## 參考資料

- Seeed Wiki：[reSpeaker Flex](https://wiki.seeedstudio.com/respeaker_flex_introduction/)、[reSpeaker Flex with XIAO ESP32S3](https://wiki.seeedstudio.com/respeaker_flex_xiao_introduction/)
- 原廠 repo：[respeaker/reSpeaker_Flex](https://github.com/respeaker/reSpeaker_Flex)（XMOS 韌體、`xvf_host.py`）
- Wiki 原始碼：[Seeed-Studio/wiki-documents](https://github.com/Seeed-Studio/wiki-documents)（`sites/en/docs/Sensor/reSpeaker_flex/`）
- XMOS：[XVF3800 Host application / Output selection](https://www.xmos.com/documentation/XM-014888-PC/html/modules/fwk_xvf/doc/user_guide/03_using_the_host_application.html#output-selection)
