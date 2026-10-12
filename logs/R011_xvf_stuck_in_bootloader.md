# R011 — 上電後 XVF3800 停在 bootloader

- 日期：2026-10-12
- 前提：R010 已經把 XVF 刷回 I2S v1.0.0，當時 smoke 全過；之後板子斷電一段時間，今天只接 XIAO 的 USB-C 上電

## Hypothesis

上電後應該直接跑 I2S 應用程式（R010 的狀態）。

## 觀察

- `smoke`：B1 PASS、i2cscan PASS（0x2C 有 ACK），但是：
  - `ver` → `ERR ver bad status status=5`；`xr 48 1 50`（BLD_MSG）、`xr 48 5 3` 也都回 status 5
  - `clkprobe` → `ws_hz~0 bck_rises=0` → XVF 沒有送出 I2S 時脈
- `dfu status` → `status=0 state=2`（dfuIDLE）→ **只有 DFU 控制器在回應，應用程式的 servicer 都不在**
  - 判斷：XVF 停在 bootloader / DFU 模式，沒有進入應用程式

## 動作

`evk_cli.py raw "dfu detach"`：叫 XVF 重開機，**不會寫入 flash**

## 結果

- 重開機後：`ver` → `1.0.0`，`BLD_MSG` → `inthost-lr48-sqr-i2c`，`clkprobe` → `ws_hz~48000`
- `smoke`：B1–B3 **全部 PASS**（L RMS −33.7 dBFS）
- GUI：已連線 COM8，音量和方向圖都正常

## 結論

- XVF 上電後偶爾會停在 bootloader；`dfu detach` 就能恢復，不需要重刷韌體
- 確切原因**還沒查清楚**，可能跟上電順序有關（只由 XIAO 供電、ESP32 開機時 I2C 上的動作），也可能跟前一次 DFU 留下的狀態有關。目前只發生過一次，先記錄
- 已經寫進 README 的疑難排解（英文和中文）。展示前先跑一次 `smoke`，遇到就用 `dfu detach`
