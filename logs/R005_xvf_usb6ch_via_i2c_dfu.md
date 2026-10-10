# R005 — 用 I2C DFU 把 XVF3800 刷成 USB 6ch 韌體

- 日期：2026-10-10
- 目的：拿到 4 支麥克風的原始訊號，用來自己做 DoA 和 beamforming，再跟 XVF 比較
- 關卡：B7（USB 模式）

## Hypothesis

把 XVF 換成 `respeaker_flex_usb_c16k6ch_v1.0.4.bin`，核心板的 USB-C 就會出現 UAC2 錄音裝置：ch1–2 是處理後的音訊，ch3–6 是 4 支麥克風的原始訊號，16 kHz。

## Baseline（刷之前）

- XVF：`VERSION = 1.0.0`、`BLD_MSG = inthost-lr48-sqr-i2c`
- 96 個可讀參數存成 `logs/R005_xvf_i2s_v1.0.0_params.json`
  - 有 6 個讀不到（status 65），都是 v1.0.2 之後才有的參數，剛好證實是 v1.0.0
- 要刷回去的話，用 `respeaker_flex_i2s_c48k2ch_v1.0.0.bin`（sha256 `41e95706…`）
  - 從版本、48k、圓形陣列推斷出來的；映像檔有壓縮過，無法從字串直接比對
- 接上核心板的 USB-C 後，**Windows 完全沒有出現 XVF 裝置**，10 分鐘監看也沒有 → I2S 映像檔沒有開 USB
- 這塊板子**沒有 SafeMode 按鈕**，也沒有 `JUMP_TO_SAFEMODE` 指令（Python 指令表裡找不到）

## 動作

1. 照 XMOS fwk_xvf 的「DFU operations」：I2C DFU 走 USB DFU 1.1 的狀態機，resid `0xF0`（`dfu_cmds.yaml`）
   - **出廠映像檔不能被覆寫**；升級映像檔無效時，bootloader 會退回出廠映像檔
2. ESP32 韌體新增 `xvf_dfu.{h,cpp}`，加上 `dfu status|begin|blk|end|abort|detach` 指令
   - `Wire.setBufferSize(256)`：一包是 3 + 130 bytes
   - 燒錄後 smoke **PASS**，原本的功能沒有退步
3. `dfu status` → `dfuIDLE status=0`：XVF 接受 I2C DFU 協定
4. PC 端 `host/xvf_i2c_dfu.py`：每次送 128 bytes，每塊都等狀態回到 `dfuDNLOAD-IDLE`

## 觀察

- 第 1 次：block 1 成功，**block 2 超過 10 秒沒回應** → PC 端逾時中止
  - 之後 ESP32 和 XVF 都正常（`ver` 有回應，DFU state = 5）
  - 字串長度測到 300 bytes 都沒問題 → 排除序列埠緩衝區的問題
  - 手動 `abort → begin → blk 0..3`：每塊 0.02 s，全部正常
  - 推測：一開始 XVF 要抹除 flash，這段時間 I2C 被卡住，超過 10 秒
  - 修正：PC 端每塊最多等 60 秒；**絕對不重送同一塊**（XVF 不檢查序號，重送會讓映像檔錯位）
- 第 2 次（每塊等 60 秒）：失敗在 block 145；第 3 次：失敗在 block **88** → **位置不固定，是間歇性問題**，跟 flash 抹除無關
  - 手動跑 700 塊都沒出事，所以是小機率事件
  - 新推測：一行 DFU 指令約 270 bytes，而 HWCDC 預設接收緩衝區只有 256 bytes，偶爾掉了換行字元 → ESP32 一直等不到完整的一行
- 修正（ESP32 韌體 + PC 端）：
  1. `Serial.setRxBufferSize(4096)`
  2. `dfu blk <seq> <hex> <sum16>`：ESP32 記錄 `next`。同一塊重送就回 `dup`，不重寫；跳號就拒絕；checksum 不對也拒絕
  3. PC 端每塊等 5 秒。逾時就問 `dfu status` 的 `next`，**只有在確定沒寫進去時才重送**
  - 燒錄後 smoke **PASS**；送錯序號會回 `ERR ... expected=0`
- 第 4 次：**7296 塊全部送完，142 秒，0 次補送** → `end: dfuIDLE`，`detach` 之後 XVF 重開機
  - 0 次補送：主要修好問題的應該是放大接收緩衝區；序號機制留著當保險

**刷完之後：**

- Windows 出現 `USB\VID_2886&PID_001E`：`reSpeaker Flex XVF3800 C16K6Ch`（UAC2）、`reSpeaker Control`、`reSpeaker DFU Factory`、HID
- USB 控制**不用 Zadig 就能用**：`xvf_host.py VERSION` → `1.0.4`，`BLD_MSG` → `ua-io16-6ch-sqr`
- sounddevice：**WDM-KS 介面有原生的 6ch @ 16 kHz**；WASAPI 只給 2ch @ 48k，MME 和 DirectSound 會被重新取樣到 44.1k
- 錄 3 秒（`captures/R005_6ch_first.wav`，本機檔）：
  - ch1 / ch2（處理後）：−49.9 / −62.2 dBFS
  - ch3–6（原始麥克風）：−84.1 / −84.3 / −83.7 / −84.2 dBFS
  - 4 支原始麥克風兩兩的相關係數 0.82–0.87 → 4 個聲道都活著，收到的是同一個聲場

## 結論

- **B7 PASS**：不需要 SafeMode 鈕，也不需要先接 USB，透過 ESP32 用 **I2C DFU** 就能更新 XVF 韌體
- 現在 XVF = USB 6ch v1.0.4。ESP32 的 I2S 路徑不再有音訊；ESP32 的 shell 和 I2C 控制還在
- 刷回 I2S：~~用 `xvf_i2c_dfu.py`~~ → **錯誤**：USB 韌體不回應 I2C，只能用 USB DFU（dfu-util）刷回去，見 R010
- 下一步：用 4 支原始麥克風訊號自己做 GCC-PHAT DoA 和 beamforming，跟 XVF 的 `DOA_VALUE` 及 ch1/2 比較
