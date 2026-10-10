"""Record XVF3800 processed audio over the ESP32 serial link into a WAV file.

  py -3.11 host/record_wav.py --sec 5 -o captures/test.wav
  py -3.11 host/record_wav.py --sec 5 --bits 32 --rate 48000   # needs 48k XVF image

The I2S link is started at --rate first (must match the flashed XVF image).
"""
from __future__ import annotations

import argparse
import sys
import wave
from datetime import datetime
from pathlib import Path

import numpy as np

from evk.serial_link import DEFAULT_PORT, EvkError, EvkSerial

REPO_ROOT = Path(__file__).resolve().parents[1]


def level_report(pcm: bytes, bits: int, channels: int) -> str:
    dtype, fs = (np.int16, 32768.0) if bits == 16 else (np.int32, 2147483648.0)
    x = np.frombuffer(pcm, dtype=dtype).reshape(-1, channels).astype(np.float64)
    parts = []
    for c in range(channels):
        rms = np.sqrt(np.mean(x[:, c] ** 2))
        peak = np.max(np.abs(x[:, c]))
        db = lambda v: 20 * np.log10(v / fs) if v > 0 else -999.0  # noqa: E731
        parts.append(f"ch{c}: rms={db(rms):.1f} dBFS peak={db(peak):.1f} dBFS")
    return " | ".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", default=DEFAULT_PORT)
    ap.add_argument("--sec", type=float, default=5.0)
    ap.add_argument("--bits", type=int, choices=(16, 32), default=16)
    ap.add_argument("--rate", type=int, choices=(16000, 48000), default=16000)
    ap.add_argument("-o", "--out", type=Path)
    args = ap.parse_args()

    out = args.out or REPO_ROOT / "captures" / f"rec_{datetime.now():%Y%m%d_%H%M%S}.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        with EvkSerial(args.port) as link:
            link.command(f"i2s start {args.rate}")
            rec = link.record(int(args.sec * 1000), args.bits)
    except (EvkError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    with wave.open(str(out), "wb") as w:
        w.setnchannels(rec.channels)
        w.setsampwidth(rec.bits // 8)
        w.setframerate(rec.rate)
        w.writeframes(rec.pcm)
    print(f"saved {out} ({rec.rate} Hz, {rec.channels} ch, {rec.bits} bit, {len(rec.pcm)} bytes)")
    print(rec.trailer)
    print(level_report(rec.pcm, rec.bits, rec.channels))
    return 0


if __name__ == "__main__":
    sys.exit(main())
