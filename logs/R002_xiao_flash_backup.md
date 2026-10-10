# R002 — B0.5 備份 XIAO 整顆 flash

- 日期：2026-10-10
- 關卡：B0.5

## Hypothesis

用 esptool 的 `read_flash` 可以完整讀出 8 MB flash（只讀），之後隨時能刷回原狀。

## 動作

`.\scripts\backup_xiao_flash.ps1 -Port COM8`

## 觀察

- `Read 8388608 bytes at 0x00000000 in 729.0 seconds (92.1 kbit/s)`
  - USB-Serial/JTAG 讀得很慢，約 12 分鐘
- 備份檔：`captures/xiao_flash_backup_20261010_150137.bin`（只存在本機，不進 git）
  - sha256 `b4f761882ffa9d892569e39fa5e745f64434894811a9e0ba1b0e0841cf3fcbd6`
- 晶片：ESP32-S3 (QFN56) rev v0.2，8 MB flash + 8 MB PSRAM，MAC `68:ee:8f:46:45:b0`
- Partition table（`default_8MB.csv`）：nvs 0x9000、otadata 0xe000、app0 0x10000、app1 0x340000、spiffs 0x670000、coredump 0x7f0000
- **重要：板子上原本跑的不是 Seeed 出廠韌體。**
  - app 裡的字串路徑是 `C:/Users/<user>/.platformio/...` 和 `.pio/libdeps/xiao_esp32s3/audio-tools/...`，代表是在這台電腦上編出來的
  - 對應的專案：本機先前的一個 PlatformIO 專案（`XMOS/src/main.cpp`，2026-09-07；不在本 repo）
  - 它的做法：ESP32 當 I2S master，16 kHz、2ch、32-bit。讀到的每個 int32 都 `>>16` 轉成 int16，L/R 交錯著往 Serial 送
  - 所以 R001 看到的 38.9 KB/s 串流，就是這支程式的輸出

## 結論

- B0.5 **PASS**，可以刷回原狀：
  `esptool.py --chip esp32s3 --port COM8 write_flash 0 captures\xiao_flash_backup_20261010_150137.bin`
- 線索：R001 分析那段串流，相鄰 sample 的差值 / 標準差 ≈ 1.3，**不像真的音訊**
  - 推測上次 9/7 的嘗試收到的是雜訊或沒對齊的資料
  - B3 要優先排查三件事：
    1. XVF 映像檔是 16k 還是 48k
    2. 誰當 master
    3. 資料的位元對齊
- 下一步：B1 燒錄 bring-up shell
