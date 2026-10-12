"""Write a Markdown table of the XVF3800 AGC / AEC / beamforming / noise-suppression
parameters with their current values.

  py -3.11 host/xvf_params_report.py                 # live values over the ESP32 (COM port must be free)
  py -3.11 host/xvf_params_report.py --baseline      # values from logs/R005_xvf_i2s_v1.0.0_params.json

Output: docs/xvf3800_params_agc_aec_bf.md
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date
from pathlib import Path

from evk import xvf_table
from evk.serial_link import EvkError, EvkSerial
from evk_cli import xvf_get

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE = REPO_ROOT / "logs" / "R005_xvf_i2s_v1.0.0_params.json"
OUT = REPO_ROOT / "docs" / "xvf3800_params_agc_aec_bf.md"

# (name, plain-language note). Notes are written from the vendor descriptions in xvf_host.py.
GROUPS = {
    "AGC 自動增益（後處理，resid 17）": [
        ("PP_AGCONOFF", "AGC 開關（0 關 / 1 開）"),
        ("PP_AGCMAXGAIN", "最大放大倍數（線性；32 ≈ +30 dB）"),
        ("PP_AGCDESIREDLEVEL", "目標輸出功率（0.0045 ≈ −23.5 dBFS）"),
        ("PP_AGCGAIN", "**目前**的放大倍數（會自己變）"),
        ("PP_AGCTIME", "一般升降音量的時間常數（秒）"),
        ("PP_AGCFASTTIME", "遇到峰值時快速降音量的時間常數（秒）"),
        ("PP_AGCALPHAFASTGAIN", "啟動快速模式的增益門檻"),
        ("PP_AGCALPHASLOW", "估計語音功率的慢速記憶（越接近 1 越平滑）"),
        ("PP_AGCALPHAFAST", "估計語音功率的快速記憶"),
        ("PP_ATTNS_MODE", "沒人講話時額外降低 AGC 增益（0 關 / 1 開）"),
        ("PP_ATTNS_NOMINAL", "沒人講話時額外降低的量（標準音量下）"),
        ("PP_ATTNS_SLOPE", "講話越小聲（AGC 放越大）時，靜音段多壓的程度"),
        ("PP_LIMITONOFF", "限幅器開關"),
        ("PP_LIMITPLIMIT", "限幅器最大輸出功率（0.47 ≈ −3.3 dBFS）"),
    ],
    "AEC 回音消除（resid 33 / 35 / 17）": [
        ("SHF_BYPASS", "整個 AEC / beamformer 區塊 bypass（0 = 有在處理）"),
        ("AEC_NUM_FARENDS", "遠端參考訊號（喇叭播放）的路數"),
        ("AEC_AECCONVERGED", "AEC 是否已收斂（要有播放參考訊號才會收斂）"),
        ("AEC_AECPATHCHANGE", "偵測到回音路徑改變"),
        ("AEC_HPFONOFF", "麥克風高通濾波（0 關，1/2/3/4 = 70/125/150/180 Hz）"),
        ("AEC_AECSILENCELEVEL", "自適應濾波器判斷有訊號的功率門檻（設定值, 目前值）"),
        ("AEC_AECEMPHASISONOFF", "AEC 的預強調／去強調濾波（0 關 / 1 開 / 2 on_eq）"),
        ("AEC_FAR_EXTGAIN", "遠端參考訊號的外部增益（dB）"),
        ("AEC_PCD_COUPLINGI", "回音路徑改變偵測（PCD）的靈敏度"),
        ("AEC_PCD_MINTHR", "PCD 最小門檻"),
        ("AEC_PCD_MAXTHR", "PCD 最大門檻"),
        ("AEC_RT60", "估計的房間殘響時間 RT60（秒；負值或趨近 0 的極小值 = 還沒有有效估計）"),
        ("AUDIO_MGR_REF_GAIN", "參考訊號進 AEC 前的增益"),
        ("AUDIO_MGR_SYS_DELAY", "參考訊號的延遲（samples），用來對齊喇叭到麥克風的時間"),
        ("AUDIO_MGR_FAR_END_DSP_ENABLE", "遠端（播放端）DSP 開關"),
        ("PP_ECHOONOFF", "殘留回音抑制開關（後處理）"),
        ("PP_GAMMA_E", "回音過度扣除係數（直接音和早期反射）"),
        ("PP_GAMMA_ETAIL", "回音過度扣除係數（殘響尾巴）"),
        ("PP_GAMMA_ENL", "非線性回音的過度扣除係數"),
        ("PP_NLATTENONOFF", "非線性回音衰減開關"),
        ("PP_NLAEC_MODE", "非線性 AEC 訓練模式（0 normal / 1 train / 2 train2）"),
        ("PP_MGSCALE", "回音抑制的最小增益比例（max, min, cur）"),
        ("PP_FMIN_SPEINDEX", "雙方同時講話時，低於這個頻率的部分壓得更多"),
        ("PP_DTSENSITIVE", "回音抑制 vs 雙方同時講話的取捨（越低越壓回音）"),
    ],
    "Beamforming / DoA（resid 33 / 35 / 20）": [
        ("AEC_NUM_MICS", "麥克風數量"),
        ("AEC_MIC_ARRAY_TYPE", "陣列類型（1 線性 / 2 方形或圓形）"),
        ("AEC_MIC_ARRAY_GEO", "麥克風座標（x, y, z）× 4，單位公尺"),
        ("AEC_AZIMUTH_VALUES", "beam 方位（弧度）：beam1、beam2、自由掃描、自動選擇"),
        ("AEC_SPENERGY_VALUES", "各 beam 的語音能量（> 0 代表有人講話）"),
        ("AEC_FIXEDBEAMSONOFF", "固定 beam 模式開關"),
        ("AEC_FIXEDBEAMSAZIMUTH_VALUES", "固定 beam 1 / 2 的方位（弧度）。出廠讀到 0, 0；baseline 裡的 1.571 / 4.712（90° / 270°）是先前 GUI 測試留下的暫時值"),
        ("AEC_FIXEDBEAMSELEVATION_VALUES", "固定 beam 1 / 2 的仰角（弧度）"),
        ("AEC_FIXEDBEAMSGATING", "固定 beam 依語音能量自動靜音不活躍的 beam"),
        ("AEC_FIXEDBEAMNOISETHR", "固定 beam 模式下，噪音消除器更新的門檻"),
        ("AEC_ASROUTONOFF", "ASR 輸出（1 = 每聲道對應一個 beam；0 = 每支麥克風的 AEC 殘差）"),
        ("AEC_ASROUTGAIN", "ASR 輸出的固定增益（線性）"),
        ("AUDIO_MGR_MIC_GAIN", "麥克風進 AEC / beamformer 前的增益"),
        ("AUDIO_MGR_SELECTED_AZIMUTHS", "beam 選擇結果（弧度）：處理後 DoA、自動選擇 beam"),
        ("AUDIO_MGR_SELECTED_CHANNELS", "送到「使用者選擇輸出」的聲道"),
        ("AUDIO_MGR_OP_L", "左聲道輸出路由（category, source）"),
        ("AUDIO_MGR_OP_R", "右聲道輸出路由（category, source）"),
        ("DOA_VALUE", "聲源方向（度）, 有沒有人講話（Seeed 加的指令）"),
    ],
    "降噪（後處理，resid 17）": [
        ("PP_MIN_NS", "穩態噪音抑制的增益下限（越小壓越多）"),
        ("PP_MIN_NN", "非穩態噪音抑制的增益下限（越小壓越多）"),
    ],
}

# Values that change on their own: shown, but flagged as a snapshot.
LIVE = {"PP_AGCGAIN", "AEC_AECCONVERGED", "AEC_AECPATHCHANGE", "AEC_RT60", "AEC_AZIMUTH_VALUES",
        "AEC_SPENERGY_VALUES", "AUDIO_MGR_SELECTED_AZIMUTHS", "DOA_VALUE", "AEC_AECSILENCELEVEL", "PP_MGSCALE"}


def fmt(v) -> str:
    vals = v if isinstance(v, (list, tuple)) else [v]
    out = []
    for x in vals:
        if isinstance(x, float):
            out.append("0" if x == 0 else (f"{x:.4g}" if abs(x) >= 1e-3 else f"{x:.3e}"))
        else:
            out.append(str(x))
    return ", ".join(out)


def db_hint(name: str, v) -> str:
    x = v[0] if isinstance(v, (list, tuple)) else v
    if not isinstance(x, (int, float)) or x <= 0:
        return ""
    if name in ("PP_AGCMAXGAIN", "PP_AGCGAIN", "AEC_ASROUTGAIN"):
        return f"≈ {20 * math.log10(x):+.1f} dB"
    if name in ("PP_AGCDESIREDLEVEL", "PP_LIMITPLIMIT"):
        return f"≈ {10 * math.log10(x):.1f} dBFS"
    return ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--baseline", action="store_true", help="use the saved baseline instead of the board")
    ap.add_argument("--port")
    args = ap.parse_args()
    table = xvf_table.load()

    values, source = {}, ""
    if not args.baseline:
        try:
            with EvkSerial(args.port) as link:
                build = xvf_get(link, table["BLD_MSG"])
                ver = ".".join(map(str, xvf_get(link, table["VERSION"])))
                for names in GROUPS.values():
                    for n, _ in names:
                        try:
                            values[n] = xvf_get(link, table[n])
                        except EvkError as e:
                            values[n] = f"n/a ({e})"
            source = f"即時讀取，XVF {ver} `{build}`，{date.today()}"
        except (EvkError, OSError) as e:
            print(f"board not available ({e}); falling back to the baseline", file=sys.stderr)
    if not values:
        base = json.loads(BASELINE.read_text(encoding="utf-8"))
        values = {n: base.get(n, "n/a（這版韌體沒有）") for names in GROUPS.values() for n, _ in names}
        source = f"`{BASELINE.relative_to(REPO_ROOT).as_posix()}`（I2S v1.0.0 `inthost-lr48-sqr-i2c`，R005 刷韌體前記錄；R010 確認刷回後 78 個設定參數一致，但方位類參數當時沒有比對）"

    lines = [
        "# XVF3800 參數：AGC / AEC / Beamforming / 降噪",
        "",
        f"- 數值來源：{source}",
        "- 產生方式：`py -3.11 host/xvf_params_report.py`（加 `--baseline` 用存檔值）",
        "- 標 🔄 的是即時狀態，會自己變；表中是當下的快照",
        "- 修改：`py -3.11 host/evk_cli.py set <名稱> <值...>`，或 GUI 的參數表。改動都是暫時的，除非寫入 `SAVE_CONFIGURATION`",
        "",
    ]
    for group, names in GROUPS.items():
        lines += [f"## {group}", "", "| 參數 | 目前的值 | 換算 | 存取 | 說明 |", "|---|---|---|---|---|"]
        for n, note in names:
            p = table[n]
            v = values[n]
            val = v if isinstance(v, str) else fmt(v)
            hint = "" if isinstance(v, str) else db_hint(n, v)
            live = " 🔄" if n in LIVE else ""
            lines.append(f"| `{n}`{live} | {val} | {hint} | {p.access} | {note} |")
        lines.append("")
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT} ({sum(len(v) for v in GROUPS.values())} parameters) - {source}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
