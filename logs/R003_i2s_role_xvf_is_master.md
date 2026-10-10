# R003 — B1–B4：I2S 收到雜訊 → 原因是 XVF3800 才是 clock master

- 日期：2026-10-10
- 關卡：B1、B2、B3、B4

## Hypothesis

一開始照 Seeed README 的說法（Flex 的 i2s 映像檔是 slave），讓 ESP32 當 I2S master、跑 16 kHz，應該就能收到處理後的音訊。

## 動作與觀察

### B1：燒錄 bring-up shell — PASS

- `pio run -t upload` 寫入 304 KB，9 秒
- `info` 有回應：ESP32-S3、8 MB flash、8 MB PSRAM

### B2：I2C 控制 — PASS

- `i2cscan`：`0x18`（aic3104）、`0x2C`（xvf3800）
- `VERSION` = **1.0.0**
- `BLD_MSG` = **`inthost-lr48-sqr-i2c`** → I2S 介面、**48 kHz**
- 出廠輸出路由：`AUDIO_MGR_OP_L = (8,0)`（使用者選的輸出 0），`AUDIO_MGR_OP_R = (7,3)`（ASR beam 3）

### B3：I2S 收音 — 先失敗，換角色後 PASS

1. ESP32 當 master，16k 和 48k 都試了：L/R 的 RMS 約 **−6 dBFS**、峰值 **0 dBFS**，每個 sample 都不是 0 → 滿幅度的垃圾資料
2. ESP32 的 I2S 已經**關掉**，XVF 還是回報 `I2S_INACTIVE = 0` → 懷疑 XVF 自己在送時脈
3. 新增 `clkprobe` 指令（ESP32 I2S 關掉時，輪詢 GPIO 數邊緣）：**`ws_hz~48000`**、BCK 和 DIN 都在跳 → **證實 XVF3800 是 master**
4. A/B 對照（同一塊板子、同一個環境，只換角色）：

   | ESP32 角色 | L RMS | L 峰值 | R RMS |
   |---|---|---|---|
   | master 48k | −6.2 dBFS | −0.0 | −6.2 |
   | **slave 48k** | **−39 ～ −48 dBFS** | −23 ～ −33 | −57 ～ −62 |
   | slave，標示成 16k | −38 ～ −48 dBFS | | |

   - 標示成 16k 時，「1 秒的 frames」0.33 秒就收滿了 → 實際取樣率是 48k，由 XVF 決定
5. 頻譜檢查（`captures/R003_quiet_48k.raw`）：
   - 低頻（50 Hz–1 kHz）比高頻（8–20 kHz）多 **64 dB**，頻譜平坦度 **0.000**
   - 白雜訊對照組：0 dB、0.562
   - → 收到的是真的聲音
   - 8 kHz 以上幾乎是空的，符合 XVF 內部用 16 kHz 處理、再升頻到 48k
6. 用筆電喇叭放 1 kHz 測試音：RMS 上升 7–9 dB，**但頻譜上沒有 1 kHz 的峰**
   - 處理後的輸出和原始麥克風（暫時改成 `OP=(1,0)/(1,1)`，測完已改回 `(8,0)/(7,3)`，沒有存檔）都一樣
   - **這項還沒有結論**：可能是 Windows 的預設輸出是藍牙裝置，或喇叭離板子太遠。要人實際講話或拍手來驗證

### B4：錄成 WAV — PASS（技術面）

- `record_wav.py --sec 5` → `captures/R003_b4_room_48k.wav`，48 kHz、2ch、16-bit、960000 bytes，**`padded=0`**
- 串口頻寬：48k × 2ch × 16-bit = 192 KB/s，2 秒剛好收到 384000 bytes，一筆都沒掉
- 位準：ch0 RMS −48.8 / 峰值 −32.4 dBFS；ch1 RMS −63.5 / 峰值 −50.7 dBFS

## 結論

- **根本原因：這塊板子上的 XVF3800 映像檔是 I2S clock master，ESP32 必須當 slave。**
  - 這跟 Seeed `xmos_firmwares/README.md` 寫的相反，也解釋了 9/7 那次為什麼收到雜訊（R002）
- 韌體預設改成 `slave` + `48000`（`board_pins.h`）。smoke test 加了兩項檢查：「XVF 有在送 48 kHz WS」和「RMS < −15 dBFS」
- B1–B3 smoke **PASS**，B4 技術面 **PASS**
- **還差的一項：用真人講話或拍手做大聲／安靜的 A/B，確認音量包絡跟著變**（下一個日誌）
- 小問題：第一次 smoke 時，master 模式的 `i2s start` 超過 5 秒才回應。改成 slave 之後沒再出現，先記下來
