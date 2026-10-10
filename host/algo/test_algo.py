"""Offline checks for the array algorithms with synthetic plane waves (no hardware).

  py -3.11 -m algo.test_algo        (run from host/)
"""
from __future__ import annotations

import numpy as np

from .array import FLEX_CIRCULAR_MICS, arrival_delays, spatial_alias_hz
from .srp_phat import SrpPhat

FS = 16000


def plane_wave(az_deg: float, n: int, snr_db: float, rng, mics=FLEX_CIRCULAR_MICS) -> np.ndarray:
    """Band-limited noise source at az_deg, fractional delays applied in the frequency domain,
    plus independent sensor noise at the given SNR."""
    src = rng.standard_normal(n)
    S = np.fft.rfft(src)
    f = np.fft.rfftfreq(n, 1 / FS)
    S[(f < 200) | (f > 4000)] = 0
    tau = arrival_delays(mics, np.array([az_deg]))[0]
    x = np.stack([np.fft.irfft(S * np.exp(-2j * np.pi * f * t), n) for t in tau], axis=1)
    x /= x.std()
    noise = rng.standard_normal(x.shape) * 10 ** (-snr_db / 20)
    return x + noise


def ang_err(a: float, b: float) -> float:
    return abs((a - b + 180) % 360 - 180)


def test_srp_phat_grid(snr_db: float = 10.0) -> float:
    rng = np.random.default_rng(1)
    doa = SrpPhat(FLEX_CIRCULAR_MICS, FS)
    errs = []
    for az in np.arange(0, 360, 15):
        r = doa.process(plane_wave(az, 1024, snr_db, rng))
        errs.append(ang_err(r.azimuth, az))
    worst = max(errs)
    print(f"SRP-PHAT  SNR {snr_db:>4.0f} dB: mean err {np.mean(errs):4.1f} deg, worst {worst:4.1f} deg over 24 directions")
    return worst


if __name__ == "__main__":
    print(f"array: square 44.4 mm, spatial alias above {spatial_alias_hz(FLEX_CIRCULAR_MICS):.0f} Hz")
    assert test_srp_phat_grid(20) <= 2.0
    assert test_srp_phat_grid(10) <= 3.0
    test_srp_phat_grid(0)
    print("OK")
