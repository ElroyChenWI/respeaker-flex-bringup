"""Beamforming A/B: does a beam aimed at the talker pick them up louder than one aimed away?

Keep talking from ONE spot next to the board for the whole run (~20 s):
  py -3.11 host/beam_test.py

1. locate   - read the auto-select beam azimuth while speech energy > 0
2. test 1   - fixed beam 1 -> talker, beam 2 -> opposite; record L=beam1, R=beam2
3. test 2   - swap the two azimuths and record again (cancels any L/R gain mismatch)
selectivity = (diff1 - diff2) / 2, where diff = speech-frame RMS(L) - RMS(R)

All XVF3800 settings touched here are restored at the end and never saved to flash.
"""
from __future__ import annotations

import argparse
import math
import sys
import time
import wave
from pathlib import Path

import numpy as np

from evk import xvf_table
from evk.serial_link import DEFAULT_PORT, EvkError, EvkSerial
from evk_cli import xvf_get, xvf_set

REPO_ROOT = Path(__file__).resolve().parents[1]
TOUCHED = [
    "AUDIO_MGR_OP_L",
    "AUDIO_MGR_OP_R",
    "AEC_FIXEDBEAMSAZIMUTH_VALUES",
    "AEC_FIXEDBEAMSELEVATION_VALUES",
    "AEC_FIXEDBEAMSGATING",
    "AEC_FIXEDBEAMSONOFF",
]
PROCESSED_BEAMS = 6  # AUDIO_MGR_OP category: 0/1 = focused (fixed) beams


def locate(link, T, seconds: float) -> tuple[float, int]:
    """Circular mean of the auto-select beam azimuth over frames with speech."""
    xs, ys = [], []
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        energy = xvf_get(link, T["AEC_SPENERGY_VALUES"])[3]
        if energy > 0:
            az = xvf_get(link, T["AEC_AZIMUTH_VALUES"])[3]
            xs.append(math.cos(az))
            ys.append(math.sin(az))
        time.sleep(0.1)
    if len(xs) < 5:
        raise EvkError(f"only {len(xs)} speech frames seen - talk louder / closer and retry")
    return math.atan2(sum(ys), sum(xs)) % (2 * math.pi), len(xs)


def speech_rms_db(pcm: bytes, rate: int) -> tuple[float, float]:
    """RMS of L and R over the loudest 30% of 20 ms blocks (speech, not pauses)."""
    x = np.frombuffer(pcm, np.int32).reshape(-1, 2).astype(np.float64) / 2**31
    block = rate // 50
    n = len(x) // block
    blocks = x[: n * block].reshape(n, block, 2)
    power = np.mean(blocks**2, axis=1)  # (n, 2)
    loud = np.argsort(power.sum(axis=1))[-max(1, int(n * 0.3)) :]
    rms = np.sqrt(power[loud].mean(axis=0))
    return tuple(20 * np.log10(r + 1e-12) for r in rms)


def save_wav(path: Path, pcm: bytes, rate: int) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(4)
        w.setframerate(rate)
        w.writeframes(pcm)


def run_case(link, T, az1: float, az2: float, sec: float, tag: str) -> float:
    xvf_set(link, T["AEC_FIXEDBEAMSAZIMUTH_VALUES"], [az1, az2])
    time.sleep(1.5)  # let the beamformer / noise suppressor settle on the new steering (dry run: 0.5 s was not enough)
    rec = link.record(int(sec * 1000), 32)
    out = REPO_ROOT / "captures" / f"beam_{tag}.wav"
    save_wav(out, rec.pcm, rec.rate)
    l_db, r_db = speech_rms_db(rec.pcm, rec.rate)
    print(f"  {tag}: beam1={math.degrees(az1):5.1f} deg  beam2={math.degrees(az2):5.1f} deg  "
          f"L={l_db:6.1f} dBFS  R={r_db:6.1f} dBFS  L-R={l_db - r_db:+5.1f} dB  ({out.name})")
    return l_db - r_db


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", default=DEFAULT_PORT)
    ap.add_argument("--locate-sec", type=float, default=6.0)
    ap.add_argument("--sec", type=float, default=5.0, help="recording length per case")
    ap.add_argument("--pass-db", type=float, default=3.0)
    args = ap.parse_args()

    T = xvf_table.load()
    with EvkSerial(args.port) as link:
        saved = {n: xvf_get(link, T[n]) for n in TOUCHED}
        try:
            link.command("i2s start", timeout=10)
            print(f">>> 開始講話，從同一個位置一直講到結束（約 {args.locate_sec + 2 * args.sec + 2:.0f} 秒）")
            theta, frames = locate(link, T, args.locate_sec)
            away = (theta + math.pi) % (2 * math.pi)
            print(f"  located talker at {math.degrees(theta):.1f} deg ({frames} speech frames)")

            xvf_set(link, T["AEC_FIXEDBEAMSELEVATION_VALUES"], [0.0, 0.0])
            xvf_set(link, T["AEC_FIXEDBEAMSGATING"], [0])
            xvf_set(link, T["AEC_FIXEDBEAMSONOFF"], [1])
            xvf_set(link, T["AUDIO_MGR_OP_L"], [PROCESSED_BEAMS, 0])
            xvf_set(link, T["AUDIO_MGR_OP_R"], [PROCESSED_BEAMS, 1])

            d1 = run_case(link, T, theta, away, args.sec, "test1_toward_away")
            d2 = run_case(link, T, away, theta, args.sec, "test2_away_toward")
            print(">>> 可以停了")
        finally:
            for n in reversed(TOUCHED):  # FIXEDBEAMSONOFF first, routing last
                xvf_set(link, T[n], list(saved[n]))
            restored = {n: xvf_get(link, T[n]) for n in TOUCHED}
            ok = all(np.allclose(restored[n], saved[n]) for n in TOUCHED)
            print(f"  settings restored: {'yes' if ok else 'NO - check ' + str(restored)}")

    selectivity = (d1 - d2) / 2
    gain_mismatch = (d1 + d2) / 2
    verdict = "PASS" if d1 > 0 > d2 and selectivity >= args.pass_db else "FAIL"
    print(f"selectivity = {selectivity:+.1f} dB (toward vs away), L/R gain mismatch = {gain_mismatch:+.1f} dB")
    print(f"BEAM {verdict} (needs test1 L>R, test2 L<R, selectivity >= {args.pass_db} dB)")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except EvkError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
