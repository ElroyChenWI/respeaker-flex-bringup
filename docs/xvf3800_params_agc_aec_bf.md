# XVF3800 參數：AGC / AEC / Beamforming / 降噪

- 數值來源：`logs/R005_xvf_i2s_v1.0.0_params.json`（I2S v1.0.0 `inthost-lr48-sqr-i2c`，R005 刷韌體前記錄；R010 確認刷回後 78 個設定參數一致，但方位類參數當時沒有比對）
- 產生方式：`py -3.11 host/xvf_params_report.py`（加 `--baseline` 用存檔值）
- 標 🔄 的是即時狀態，會自己變；表中是當下的快照
- 修改：`py -3.11 host/evk_cli.py set <名稱> <值...>`，或 GUI 的參數表。改動都是暫時的，除非寫入 `SAVE_CONFIGURATION`

## AGC 自動增益（後處理，resid 17）

| 參數 | 目前的值 | 換算 | 存取 | 說明 |
|---|---|---|---|---|
| `PP_AGCONOFF` | 1 |  | rw | AGC 開關（0 關 / 1 開） |
| `PP_AGCMAXGAIN` | 32 | ≈ +30.1 dB | rw | 最大放大倍數（線性；32 ≈ +30 dB） |
| `PP_AGCDESIREDLEVEL` | 0.0045 | ≈ -23.5 dBFS | rw | 目標輸出功率（0.0045 ≈ −23.5 dBFS） |
| `PP_AGCGAIN` 🔄 | 32 | ≈ +30.1 dB | rw | **目前**的放大倍數（會自己變） |
| `PP_AGCTIME` | 0.9 |  | rw | 一般升降音量的時間常數（秒） |
| `PP_AGCFASTTIME` | 0.1 |  | rw | 遇到峰值時快速降音量的時間常數（秒） |
| `PP_AGCALPHAFASTGAIN` | 0 |  | rw | 啟動快速模式的增益門檻 |
| `PP_AGCALPHASLOW` | 0.984 |  | rw | 估計語音功率的慢速記憶（越接近 1 越平滑） |
| `PP_AGCALPHAFAST` | 0.36 |  | rw | 估計語音功率的快速記憶 |
| `PP_ATTNS_MODE` | 0 |  | rw | 沒人講話時額外降低 AGC 增益（0 關 / 1 開） |
| `PP_ATTNS_NOMINAL` | 1 |  | rw | 沒人講話時額外降低的量（標準音量下） |
| `PP_ATTNS_SLOPE` | 1 |  | rw | 講話越小聲（AGC 放越大）時，靜音段多壓的程度 |
| `PP_LIMITONOFF` | 1 |  | rw | 限幅器開關 |
| `PP_LIMITPLIMIT` | 0.47 | ≈ -3.3 dBFS | rw | 限幅器最大輸出功率（0.47 ≈ −3.3 dBFS） |

## AEC 回音消除（resid 33 / 35 / 17）

| 參數 | 目前的值 | 換算 | 存取 | 說明 |
|---|---|---|---|---|
| `SHF_BYPASS` | 0 |  | rw | 整個 AEC / beamformer 區塊 bypass（0 = 有在處理） |
| `AEC_NUM_FARENDS` | 1 |  | ro | 遠端參考訊號（喇叭播放）的路數 |
| `AEC_AECCONVERGED` 🔄 | 0 |  | ro | AEC 是否已收斂（要有播放參考訊號才會收斂） |
| `AEC_AECPATHCHANGE` 🔄 | 0 |  | ro | 偵測到回音路徑改變 |
| `AEC_HPFONOFF` | 2 |  | rw | 麥克風高通濾波（0 關，1/2/3/4 = 70/125/150/180 Hz） |
| `AEC_AECSILENCELEVEL` 🔄 | 1.000e-09, 1.000e-06 |  | rw | 自適應濾波器判斷有訊號的功率門檻（設定值, 目前值） |
| `AEC_AECEMPHASISONOFF` | 2 |  | rw | AEC 的預強調／去強調濾波（0 關 / 1 開 / 2 on_eq） |
| `AEC_FAR_EXTGAIN` | 0 |  | rw | 遠端參考訊號的外部增益（dB） |
| `AEC_PCD_COUPLINGI` | -1 |  | rw | 回音路徑改變偵測（PCD）的靈敏度 |
| `AEC_PCD_MINTHR` | 0.005 |  | rw | PCD 最小門檻 |
| `AEC_PCD_MAXTHR` | 0.1 |  | rw | PCD 最大門檻 |
| `AEC_RT60` 🔄 | 1.401e-45 |  | ro | 估計的房間殘響時間 RT60（秒；負值或趨近 0 的極小值 = 還沒有有效估計） |
| `AUDIO_MGR_REF_GAIN` | 1.9 |  | rw | 參考訊號進 AEC 前的增益 |
| `AUDIO_MGR_SYS_DELAY` | -30 |  | rw | 參考訊號的延遲（samples），用來對齊喇叭到麥克風的時間 |
| `AUDIO_MGR_FAR_END_DSP_ENABLE` | 0 |  | rw | 遠端（播放端）DSP 開關 |
| `PP_ECHOONOFF` | 1 |  | rw | 殘留回音抑制開關（後處理） |
| `PP_GAMMA_E` | 1 |  | rw | 回音過度扣除係數（直接音和早期反射） |
| `PP_GAMMA_ETAIL` | 1 |  | rw | 回音過度扣除係數（殘響尾巴） |
| `PP_GAMMA_ENL` | 1.1 |  | rw | 非線性回音的過度扣除係數 |
| `PP_NLATTENONOFF` | 0 |  | rw | 非線性回音衰減開關 |
| `PP_NLAEC_MODE` | 0 |  | rw | 非線性 AEC 訓練模式（0 normal / 1 train / 2 train2） |
| `PP_MGSCALE` 🔄 | 1, 1, 1 |  | rw | 回音抑制的最小增益比例（max, min, cur） |
| `PP_FMIN_SPEINDEX` | 0 |  | rw | 雙方同時講話時，低於這個頻率的部分壓得更多 |
| `PP_DTSENSITIVE` | 12 |  | rw | 回音抑制 vs 雙方同時講話的取捨（越低越壓回音） |

## Beamforming / DoA（resid 33 / 35 / 20）

| 參數 | 目前的值 | 換算 | 存取 | 說明 |
|---|---|---|---|---|
| `AEC_NUM_MICS` | 4 |  | ro | 麥克風數量 |
| `AEC_MIC_ARRAY_TYPE` | 2 |  | ro | 陣列類型（1 線性 / 2 方形或圓形） |
| `AEC_MIC_ARRAY_GEO` | 0.0222, -0.0222, 0, 0.0222, 0.0222, 0, -0.0222, 0.0222, 0, -0.0222, -0.0222, 0 |  | ro | 麥克風座標（x, y, z）× 4，單位公尺 |
| `AEC_AZIMUTH_VALUES` 🔄 | 3.621, 0.2853, 3.637, 3.621 |  | ro | beam 方位（弧度）：beam1、beam2、自由掃描、自動選擇 |
| `AEC_SPENERGY_VALUES` 🔄 | 0, 0, 0, 0 |  | ro | 各 beam 的語音能量（> 0 代表有人講話） |
| `AEC_FIXEDBEAMSONOFF` | 0 |  | rw | 固定 beam 模式開關 |
| `AEC_FIXEDBEAMSAZIMUTH_VALUES` | 1.571, 4.712 |  | rw | 固定 beam 1 / 2 的方位（弧度）。出廠讀到 0, 0；baseline 裡的 1.571 / 4.712（90° / 270°）是先前 GUI 測試留下的暫時值 |
| `AEC_FIXEDBEAMSELEVATION_VALUES` | 0, 0 |  | rw | 固定 beam 1 / 2 的仰角（弧度） |
| `AEC_FIXEDBEAMSGATING` | 0 |  | rw | 固定 beam 依語音能量自動靜音不活躍的 beam |
| `AEC_FIXEDBEAMNOISETHR` | 0.4, 0.4 |  | rw | 固定 beam 模式下，噪音消除器更新的門檻 |
| `AEC_ASROUTONOFF` | 1 |  | rw | ASR 輸出（1 = 每聲道對應一個 beam；0 = 每支麥克風的 AEC 殘差） |
| `AEC_ASROUTGAIN` | 1 | ≈ +0.0 dB | rw | ASR 輸出的固定增益（線性） |
| `AUDIO_MGR_MIC_GAIN` | 10 |  | rw | 麥克風進 AEC / beamformer 前的增益 |
| `AUDIO_MGR_SELECTED_AZIMUTHS` 🔄 | 3.621, 3.621 |  | ro | beam 選擇結果（弧度）：處理後 DoA、自動選擇 beam |
| `AUDIO_MGR_SELECTED_CHANNELS` | 3, 3 |  | rw | 送到「使用者選擇輸出」的聲道 |
| `AUDIO_MGR_OP_L` | 8, 0 |  | rw | 左聲道輸出路由（category, source） |
| `AUDIO_MGR_OP_R` | 7, 3 |  | rw | 右聲道輸出路由（category, source） |
| `DOA_VALUE` 🔄 | 207, 1 |  | ro | 聲源方向（度）, 有沒有人講話（Seeed 加的指令） |

## 降噪（後處理，resid 17）

| 參數 | 目前的值 | 換算 | 存取 | 說明 |
|---|---|---|---|---|
| `PP_MIN_NS` | 0.15 |  | rw | 穩態噪音抑制的增益下限（越小壓越多） |
| `PP_MIN_NN` | 0.51 |  | rw | 非穩態噪音抑制的增益下限（越小壓越多） |
