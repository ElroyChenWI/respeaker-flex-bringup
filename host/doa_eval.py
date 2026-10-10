"""Summarise labelled doa_live runs: own SRP-PHAT vs XVF3800 DoA, per position.

  py -3.11 host/doa_eval.py                       # all captures/doa_*_true*.csv
  py -3.11 host/doa_eval.py captures/doa_..._true1.csv ...
  py -3.11 host/doa_eval.py --loudest 0.4         # judge on the loudest 40% frames instead of the gate

Reference = the XVF3800's DOA_VALUE on frames where it flags speech (no ground-truth angles
needed: --label only groups runs by position).
"""
from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]


def circ_mean(a) -> float:
    r = np.deg2rad(np.asarray(a, float))
    return float(np.rad2deg(np.arctan2(np.sin(r).mean(), np.cos(r).mean())) % 360)


def circ_std(a) -> float:
    r = np.deg2rad(np.asarray(a, float))
    R = np.hypot(np.sin(r).mean(), np.cos(r).mean())
    return float(np.rad2deg(np.sqrt(-2 * np.log(max(R, 1e-9)))))


def wrap(d):
    return (np.asarray(d, float) + 180) % 360 - 180


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", nargs="*", type=Path)
    ap.add_argument("--loudest", type=float, help="use the loudest fraction of frames instead of own_valid")
    args = ap.parse_args()
    files = args.csv or sorted(Path(p) for p in glob.glob(str(REPO_ROOT / "captures" / "doa_*_true[0-9]*.csv")))
    if not files:
        print("no labelled runs found (record with: doa_live.py --sec 10 --label <n>)")
        return 1

    print(f"{'pos':>4} {'used':>9} | {'own az':>7} {'±std':>5} | {'XVF az':>7} {'±std':>5} | {'own-XVF':>7} | "
          f"{'|diff| med':>10} {'<=10°':>6} {'<=20°':>6}")
    all_d = []
    for f in files:
        t = pd.read_csv(f)
        if args.loudest:
            sel = t[t.own_dbfs >= t.own_dbfs.quantile(1 - args.loudest)]
        else:
            sel = t[t.own_valid == 1]
        ref = t[t.xvf_speech == 1]
        pair = sel[sel.xvf_speech == 1]
        if sel.empty or ref.empty:
            print(f"{str(t.true_az.iloc[0]):>4} {len(sel):>4}/{len(t):<4} | no usable frames ({f.name})")
            continue
        d = wrap(pair.own_az - pair.xvf_doa) if len(pair) else np.array([np.nan])
        all_d.extend(d[~np.isnan(d)])
        own, xvf = circ_mean(sel.own_az), circ_mean(ref.xvf_doa)
        print(f"{str(t.true_az.iloc[0]):>4} {len(sel):>4}/{len(t):<4} | {own:7.1f} {circ_std(sel.own_az):5.1f} | "
              f"{xvf:7.1f} {circ_std(ref.xvf_doa):5.1f} | {wrap(own - xvf):+7.1f} | {np.nanmedian(np.abs(d)):10.1f} "
              f"{100 * np.mean(np.abs(d) <= 10):5.0f}% {100 * np.mean(np.abs(d) <= 20):5.0f}%")
    if all_d:
        a = np.abs(np.array(all_d))
        print(f"ALL  {len(a)} paired frames: median |own - XVF| {np.median(a):.1f} deg, "
              f"{100 * np.mean(a <= 10):.0f}% within 10 deg, {100 * np.mean(a <= 20):.0f}% within 20 deg")
    return 0


if __name__ == "__main__":
    sys.exit(main())
