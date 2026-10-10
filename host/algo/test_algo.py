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


def test_beamformers(target_az: float = 90.0, interf_az: float = 0.0) -> tuple[float, float]:
    """Target + equal-power interferer from another direction + weak sensor noise.

    Returns the SIR improvement (dB) of delay-and-sum and MVDR over a single mic,
    measured by passing target and interferer through the same weights separately."""
    from . import beamformer as bf

    rng = np.random.default_rng(3)
    n = 4 * FS
    tgt = plane_wave(target_az, n, 60, rng)
    itf = plane_wave(interf_az, n, 60, rng)
    sensor = rng.standard_normal(tgt.shape) * 10 ** (-30 / 20)
    d = bf.steering(FLEX_CIRCULAR_MICS, target_az, FS)
    Xi = bf.stft(itf + sensor)
    w_das = d / d.shape[1]
    w_mvdr = bf.mvdr_weights(bf.noise_covariance(Xi), d)  # noise covariance = interferer-only lead-in

    def sir(w):
        st = np.sum(np.abs(bf.apply_weights(bf.stft(tgt), w)) ** 2)
        si = np.sum(np.abs(bf.apply_weights(bf.stft(itf), w)) ** 2)
        return 10 * np.log10(st / si)

    base = 10 * np.log10(np.sum(tgt[:, 0] ** 2) / np.sum(itf[:, 0] ** 2))
    g_das, g_mvdr = sir(w_das) - base, sir(w_mvdr) - base
    # distortionless check: MVDR response towards the target must be 1 at every bin
    resp = np.abs(np.einsum("fm,fm->f", np.conj(w_mvdr), d))
    print(f"beamformers: target {target_az:.0f} deg, interferer {interf_az:.0f} deg -> "
          f"SIR gain DAS {g_das:+.1f} dB, MVDR {g_mvdr:+.1f} dB (MVDR target response {resp.min():.3f}..{resp.max():.3f})")
    assert np.allclose(resp[1:], 1.0, atol=1e-6)
    return g_das, g_mvdr


def test_stft_roundtrip() -> None:
    from . import beamformer as bf

    x = np.random.default_rng(4).standard_normal((FS, 1))
    y = bf.istft(bf.stft(x)[:, :, 0], len(x))
    core = slice(bf.NFFT, len(x) - bf.NFFT)
    err = np.max(np.abs(y[core] - x[core, 0]))
    print(f"STFT/ISTFT round trip: max error {err:.2e}")
    assert err < 1e-9


if __name__ == "__main__":
    print(f"array: square 44.4 mm, spatial alias above {spatial_alias_hz(FLEX_CIRCULAR_MICS):.0f} Hz")
    assert test_srp_phat_grid(20) <= 2.0
    assert test_srp_phat_grid(10) <= 3.0
    test_srp_phat_grid(0)
    test_stft_roundtrip()
    g_das, g_mvdr = test_beamformers(90, 0)
    assert g_mvdr > g_das and g_mvdr > 10
    test_beamformers(90, 180)
    test_beamformers(90, 45)
    print("OK")
