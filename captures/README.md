# captures

錄音（`*.wav` / `*.raw`）和 flash 備份（`xiao_flash_backup_*.bin`）都**只存在本機，不進 git**，因為錄音裡可能有人聲或環境對話。

- GUI 和 `record_wav.py` 錄的檔案都放在這裡
- R0XX 日誌引用的錄音也是本機檔，日誌裡記了數據和 sha256，可以拿來核對
- 唯一進 git 的是 `R001_com8_factory_10s.bin`：舊韌體在 COM 上送出的 10 秒原始資料，不是音訊（見 `logs/R001`）
