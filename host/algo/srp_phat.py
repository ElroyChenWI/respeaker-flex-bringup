"""SRP-PHAT direction of arrival.

For every frame: FFT each mic, form the PHAT-weighted cross spectrum of every mic pair
(magnitude discarded, only phase kept), then for each candidate azimuth sum the pair
cross spectra after compensating the expected inter-mic phase. The azimuth where all
pairs line up best is the estimate. With 4 mics this uses all 6 pairs at once, which is
far more robust than single-pair GCC-PHAT.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .array import arrival_delays


@dataclass
class DoaResult:
    azimuth: float        # degrees, array convention (0 = +x, CCW)
    confidence: float     # coherence at the peak, 0..1: mean over pairs/bins of the phase match
                          # (1 = every pair agrees perfectly; diffuse noise stays near 0)
    power_db: float       # frame power of the mic average, dBFS
    srp: np.ndarray       # SRP value per grid azimuth (for plotting)


class SrpPhat:
    def __init__(self, mics: np.ndarray, fs: int, nfft: int = 1024,
                 fmin: float = 300.0, fmax: float = 3800.0, grid_deg: float = 1.0):
        self.mics, self.fs, self.nfft = mics, fs, nfft
        self.grid = np.arange(0.0, 360.0, grid_deg)
        freqs = np.fft.rfftfreq(nfft, 1 / fs)
        self.band = (freqs >= fmin) & (freqs <= fmax)
        self.freqs = freqs[self.band]
        self.window = np.hanning(nfft)
        n = len(mics)
        self.pairs = [(i, j) for i in range(n) for j in range(i + 1, n)]
        tau = arrival_delays(mics, self.grid)  # (n_az, n_mics)
        # expected phase of X_i * conj(X_j) for a source at each azimuth:
        # X_i = S * exp(-j 2 pi f tau_i)  =>  X_i X_j* ~ exp(-j 2 pi f (tau_i - tau_j))
        dtau = np.stack([tau[:, i] - tau[:, j] for i, j in self.pairs], axis=-1)  # (n_az, n_pairs)
        self._steer = np.exp(-2j * np.pi * self.freqs[None, :, None] * dtau[:, None, :])  # (az, f, pair)

    def process(self, frame: np.ndarray) -> DoaResult:
        """frame: (nfft, n_mics) float samples."""
        x = frame - frame.mean(axis=0)
        power = float(np.mean(x.mean(axis=1) ** 2))
        X = np.fft.rfft(x * self.window[:, None], axis=0)[self.band]  # (f, mics)
        cross = np.stack([X[:, i] * np.conj(X[:, j]) for i, j in self.pairs], axis=-1)  # (f, pair)
        cross /= np.abs(cross) + 1e-12  # PHAT: keep phase only
        # remove the steering phase; a true source makes all terms real and positive
        srp = np.real(np.einsum("fp,afp->a", cross, np.conj(self._steer)))
        k = int(np.argmax(srp))
        # A peak-to-mean "z-score" was tried first and never exceeded ~2.5 on a 4-mic map (R006),
        # so use the normalised SRP value instead: it is bounded and physically meaningful.
        coherence = float(srp[k] / (len(self.pairs) * len(self.freqs)))
        return DoaResult(float(self.grid[k]), coherence, 10 * np.log10(power + 1e-20), srp)
