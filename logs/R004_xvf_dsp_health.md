# R004 — XVF3800 DSP 有沒有起來、有沒有正常運作

- 日期：2026-10-10
- 關卡：B4 收尾、B6 前置
- 前提：使用者已經用 `record_wav.py` 確認錄得到人聲（B4 PASS）

## Hypothesis

XVF3800 開機後，DSP pipeline（AEC → beamformer → 後處理 NS/AGC → DoA/VAD）都在跑，沒有被 bypass，運算也沒有超時。

## 動作

透過 ESP32 shell 的 `xr`，用 I2C 讀 XVF 的設定和執行期統計，每 1.5 秒讀一次，共 3 次。另外新增 `evk_cli.py dsp [--watch]`，一行顯示 DSP 的健康狀態。

## 觀察

**設定（靜態）**

| 參數 | 值 | 意思 |
|---|---|---|
| SHF_BYPASS | 0 | DSP **沒有** bypass |
| AEC_NUM_MICS / FARENDS | 4 / 1 | 4 支麥克風、1 路參考訊號 |
| AEC_MIC_ARRAY_TYPE | 2 | |
| AEC_MIC_ARRAY_GEO | 4 支在 (±22.2 mm, ±22.2 mm) | 方形排列，邊長 44.4 mm，符合「圓形 44 mm」板子 |
| PP_AGCONOFF / MAXGAIN | 1 / 32 | AGC 開著 |
| PP_ECHOONOFF / LIMITONOFF | 1 / 1 | 回音抑制、限幅器都開著 |
| PP_MIN_NS / MIN_NN | 0.15 / 0.51 | 降噪下限 |
| AUDIO_MGR_MIC_GAIN | 10.0 | |
| AUDIO_MGR_SYS_DELAY | −30 | 跟 Seeed changelog v1.0.7 的預設值一樣 |
| BOOT_STATUS | `JoF` | 從 flash 開機 |

**執行期（動態）**

- 各 DSP thread 的閒置時間都 > 0，而且一直在變動：AEC 40–59 萬、PP 34–52 萬；`AEC_MIN_IDLE_TIME` 375786、`PP_MIN_IDLE_TIME` 336969 → **沒有超時，還有很多餘裕**
- 自由掃描的 beam 方位一直在變：4.633 → 1.79 → 6.261 rad → **beamformer 在跑**
- `PP_AGCGAIN`：3.436 → 4.13 → **AGC 在動態調整**
- 安靜時 `AEC_SPENERGY_VALUES` = 0、`DOA_VALUE` = (0, 0)；過一陣子出現 `doa=341 speech=1` → **VAD 和 DoA 有反應**
- `AEC_AECCONVERGED` = 0：預期中。ESP32 的 TX 只送靜音，AEC 沒有遠端參考訊號可以收斂

## 結論

- XVF3800 的 DSP **有起來，而且正常運作**：沒有 bypass、運算有餘裕、beamformer / AGC / VAD / DoA 都有反應
- **還沒驗證：AEC（回音消除）**。要等 B5 從 ESP32 送參考訊號（播放音樂），同時錄音，看 `AEC_AECCONVERGED` 會不會變成 1、回音會不會被消掉
- DoA 準確度還沒量：要繞著板子在幾個已知角度講話，看 `doa` 跟不跟得上（B6）
