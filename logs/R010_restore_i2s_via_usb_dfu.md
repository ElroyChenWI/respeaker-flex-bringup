# R010 — 把 XVF3800 刷回出廠的 I2S 韌體（交付用的狀態）

- 日期：2026-10-10
- 目的：回到下午驗證過、可以錄音的狀態（XVF = I2S 48 kHz v1.0.0）。演算法實驗用的 USB 6ch 韌體先不用

## Hypothesis

用 R005 的反方向：ESP32 走 I2C DFU，把 `respeaker_flex_i2s_c48k2ch_v1.0.0.bin` 送回去。

## 動作與觀察

1. `xvf_i2c_dfu.py --status` → `ERR dfu status rc=i2c nack`；`get VERSION` 和 `get BLD_MSG` 也都 NACK
   - **USB 6ch 韌體不會回應 I2C**（0x2C 沒有回應），所以 I2C DFU 只能單向用：I2S → USB
2. 改走 USB DFU（核心板的 USB-C）：`dfu-util -l` →
   - `[2886:001e] alt=1 "reSpeaker DFU Upgrade"`、`alt=0 "reSpeaker DFU Factory"`
   - Windows 11 **不用 Zadig** 就能用
3. `dfu-util -R -e -a 1 -D third_party/reSpeaker_Flex/xmos_firmwares/i2s/respeaker_flex_i2s_c48k2ch_v1.0.0.bin`
   - 傳輸大小 256 → `dfuMANIFEST` → `dfuIDLE` → `Done!`，自動 reset
   - 有 `Invalid DFU suffix signature` 警告：預期中，Seeed 的映像檔本來就沒有 suffix
4. 驗證：
   - XVF 的 USB 裝置（2886:*）消失 → 回到 I2S 映像檔
   - `VERSION = 1.0.0`、`BLD_MSG = inthost-lr48-sqr-i2c`：**跟 R005 刷之前的 baseline 完全一樣**
     - 這也證實了 R005 的推斷：原本的映像檔就是 `c48k2ch_v1.0.0`
   - `evk_cli.py smoke`：B1–B3 全部 **PASS**（WS 48 kHz，L RMS −32.8 dBFS）
   - `record_wav.py --sec 5`：48 kHz / 2ch / 16-bit，`padded=0`
   - 78 個設定參數跟 `logs/R005_xvf_i2s_v1.0.0_params.json` **全部一樣**（排除一直在變的計數器和即時值）

## 結論

- **XVF3800 已經回到出廠的 I2S v1.0.0，設定跟刷之前完全一致**，是可以交付的狀態
- ESP32 維持現在的 bring-up shell（多了 `dfu` 指令；原本的功能都通過 smoke）
- 韌體切換的方向和方法：
  - I2S → USB 6ch：ESP32 走 **I2C DFU**（R005）
  - USB 6ch → I2S：核心板 USB-C 走 **USB DFU**（dfu-util）
- README 原本寫「兩個方向都能用 I2C 切換」是錯的，已經修正（英文和中文版都改了）
