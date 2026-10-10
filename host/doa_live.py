"""Live DoA: own SRP-PHAT on the 4 raw mics vs the XVF3800's own estimate.

Needs the XVF3800 USB 6ch firmware and the core-board USB-C (logs/R005).

  py -3.11 host/doa_live.py                    # live, prints ~5 lines/s, logs CSV to captures/
  py -3.11 host/doa_live.py --sec 30 --label 90   # tag a run with the true angle for evaluation
  py -3.11 host/doa_live.py --wav captures/R005_6ch_first.wav   # offline on a 6ch recording

Columns: own azimuth / confidence / frame power, XVF DOA_VALUE + speech flag, XVF auto-select
beam azimuth. Own estimates are only "valid" when confidence and level clear the gates.
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
import wave
from datetime import datetime
from pathlib import Path

import numpy as np

from algo.array import FLEX_CIRCULAR_MICS
from algo.sources import FS, RAW_MIC_CHANNELS, LiveCapture, XvfUsb, read_wav
from algo.srp_phat import SrpPhat

REPO_ROOT = Path(__file__).resolve().parents[1]
NFFT = 1024   # 64 ms analysis frame
HOP = 512     # 32 ms


class Gate:
    """Valid when SRP confidence is high and the frame is clearly above the noise floor."""

    def __init__(self, min_conf: float, margin_db: float):
        self.min_conf, self.margin_db, self.floor = min_conf, margin_db, None

    def __call__(self, power_db: float, conf: float) -> bool:
        self.floor = power_db if self.floor is None else min(power_db, self.floor + 0.02)  # slow rise, fast fall
        return conf >= self.min_conf and power_db >= self.floor + self.margin_db


def circ_mean(deg: list[float]) -> float:
    a = np.deg2rad(deg)
    return float(np.rad2deg(np.arctan2(np.sin(a).mean(), np.cos(a).mean())) % 360)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wav", type=Path, help="process a 6ch 16 kHz WAV instead of the live device")
    ap.add_argument("--sec", type=float, default=0, help="stop after N seconds (live); 0 = until Ctrl+C")
    ap.add_argument("--label", type=float, help="true source azimuth (deg) for this run, stored in the CSV")
    ap.add_argument("--min-conf", type=float, default=0.4, help="min SRP coherence 0..1 (quiet room p50 ~0.34, R006)")
    ap.add_argument("--margin-db", type=float, default=10.0, help="min level above the tracked noise floor")
    ap.add_argument("--no-wav", action="store_true", help="do not save the raw 6ch audio next to the CSV")
    args = ap.parse_args()

    doa = SrpPhat(FLEX_CIRCULAR_MICS, FS, nfft=NFFT)
    gate = Gate(args.min_conf, args.margin_db)
    out = REPO_ROOT / "captures" / f"doa_{datetime.now():%Y%m%d_%H%M%S}{'' if args.label is None else f'_true{args.label:g}'}.csv"
    out.parent.mkdir(exist_ok=True)
    rows, valid = [], []

    if args.wav:
        x = read_wav(args.wav)[:, RAW_MIC_CHANNELS]
        for k in range(0, len(x) - NFFT, HOP):
            r = doa.process(x[k:k + NFFT])
            ok = gate(r.power_db, r.confidence)
            rows.append([k / FS, round(r.azimuth, 1), round(r.confidence, 3), round(r.power_db, 1), int(ok), "", "", "", args.label])
            if ok:
                valid.append(r.azimuth)
    else:
        xvf = XvfUsb()
        buf = np.zeros((NFFT, 4), np.float32)
        audio = []
        t0 = time.monotonic()
        last_print, last_xvf = 0.0, (None, None, None)
        print(f"{'t':>6} | {'own az':>6} {'coh':>5} {'dBFS':>6} ok | {'XVF doa':>7} sp | {'XVF beam':>8}")
        try:
            with LiveCapture(block=HOP) as cap:
                while not args.sec or time.monotonic() - t0 < args.sec:
                    blk6 = cap.q.get(timeout=2)
                    audio.append(blk6)
                    blk = blk6[:, RAW_MIC_CHANNELS]
                    buf = np.vstack([buf[len(blk):], blk])
                    r = doa.process(buf)
                    ok = gate(r.power_db, r.confidence)
                    t = time.monotonic() - t0
                    if t - last_print >= 0.2:  # USB control reads are slow-ish: poll the XVF at 5 Hz
                        d, sp = xvf.doa()
                        last_xvf = (d, sp, round(xvf.auto_beam_deg(), 1))
                        last_print = t
                        print(f"{t:6.1f} | {r.azimuth:6.0f} {r.confidence:5.2f} {r.power_db:6.1f} {'Y ' if ok else '. '} | "
                              f"{d:7d} {sp:2d} | {last_xvf[2]:8.1f}", flush=True)
                    rows.append([round(t, 3), round(r.azimuth, 1), round(r.confidence, 3), round(r.power_db, 1), int(ok),
                                 *last_xvf, args.label])
                    if ok:
                        valid.append(r.azimuth)
        except KeyboardInterrupt:
            pass
        finally:
            xvf.close()
        if cap.overflows:
            print(f"warning: {cap.overflows} audio overflows")
        if audio and not args.no_wav:
            x = (np.clip(np.vstack(audio), -1, 1 - 2**-31) * 2**31).astype(np.int32)
            with wave.open(str(out.with_suffix(".wav")), "wb") as w:
                w.setnchannels(6)
                w.setsampwidth(4)
                w.setframerate(FS)
                w.writeframes(x.tobytes())

    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t", "own_az", "own_coh", "own_dbfs", "own_valid", "xvf_doa", "xvf_speech", "xvf_beam_az", "true_az"])
        w.writerows(rows)
    summary = f"{len(valid)}/{len(rows)} valid frames"
    if valid:
        summary += f", own mean azimuth {circ_mean(valid):.1f} deg"
    print(f"{summary}  ->  {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
