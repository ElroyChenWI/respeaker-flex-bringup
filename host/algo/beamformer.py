"""Frequency-domain beamformers on the raw mic channels.

STFT (sqrt-Hann analysis/synthesis, 50% overlap -> perfect reconstruction), then per bin:

  delay-and-sum   w = d / M                              (fixed, no adaptation)
  MVDR            w = R_n^-1 d / (d^H R_n^-1 d)          (R_n = noise covariance)

d = steering vector towards the target azimuth (array.steering_vectors). MVDR keeps the
target undistorted and minimises everything else; R_n is estimated from frames where the
target is silent (a noise-only lead-in), with diagonal loading for robustness.
"""
from __future__ import annotations

import numpy as np

from .array import steering_vectors

NFFT = 512
HOP = NFFT // 2


def _window() -> np.ndarray:
    return np.sqrt(np.hanning(NFFT + 1)[:NFFT])  # periodic sqrt-Hann: COLA at 50% overlap


def stft(x: np.ndarray) -> np.ndarray:
    """(n, ch) -> (frames, bins, ch)"""
    w = _window()
    n = (len(x) - NFFT) // HOP + 1
    frames = np.stack([x[i * HOP:i * HOP + NFFT] * w[:, None] for i in range(n)])
    return np.fft.rfft(frames, axis=1)


def istft(X: np.ndarray, length: int) -> np.ndarray:
    """(frames, bins) -> (length,)"""
    w = _window()
    y = np.zeros(length + NFFT)
    for i, frame in enumerate(np.fft.irfft(X, NFFT, axis=1)):
        y[i * HOP:i * HOP + NFFT] += frame * w
    return y[:length]


def steering(mics: np.ndarray, az_deg: float, fs: int) -> np.ndarray:
    """(bins, mics) steering vector for one azimuth."""
    freqs = np.fft.rfftfreq(NFFT, 1 / fs)
    return steering_vectors(mics, np.array([az_deg]), freqs)[0]


def delay_and_sum(X: np.ndarray, d: np.ndarray) -> np.ndarray:
    """X (frames, bins, mics), d (bins, mics) -> (frames, bins)"""
    w = d / d.shape[1]
    return np.einsum("fm,tfm->tf", np.conj(w), X)


def noise_covariance(X: np.ndarray) -> np.ndarray:
    """(frames, bins, mics) -> (bins, mics, mics) spatial covariance averaged over frames."""
    return np.einsum("tfm,tfn->fmn", X, np.conj(X)) / max(len(X), 1)


def mvdr_weights(Rn: np.ndarray, d: np.ndarray, loading: float = 1e-2) -> np.ndarray:
    """Rn (bins, M, M), d (bins, M) -> w (bins, M). Diagonal loading relative to the
    per-bin trace keeps it stable when the noise field is nearly rank-deficient."""
    M = d.shape[1]
    eye = np.eye(M)[None]
    tr = np.real(np.trace(Rn, axis1=1, axis2=2))[:, None, None] / M
    Ri = np.linalg.inv(Rn + loading * tr * eye + 1e-18 * eye)
    num = np.einsum("fmn,fn->fm", Ri, d)
    den = np.einsum("fm,fm->f", np.conj(d), num)
    return num / den[:, None]


def apply_weights(X: np.ndarray, w: np.ndarray) -> np.ndarray:
    return np.einsum("fm,tfm->tf", np.conj(w), X)


def beam_pattern(w: np.ndarray, mics: np.ndarray, fs: int, az_grid: np.ndarray) -> np.ndarray:
    """|response| (az, bins) of weights w (bins, M) to plane waves from each azimuth."""
    freqs = np.fft.rfftfreq(NFFT, 1 / fs)
    D = steering_vectors(mics, az_grid, freqs)  # (az, bins, M)
    return np.abs(np.einsum("fm,afm->af", np.conj(w), D))
