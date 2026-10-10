"""Microphone geometry and far-field steering.

Coordinates and angles follow the XVF3800 convention (AEC_MIC_ARRAY_GEO): metres,
azimuth 0 = +x, counter-clockwise positive, measured in the array plane.
"""
from __future__ import annotations

import numpy as np

SPEED_OF_SOUND = 343.0  # m/s at ~20 C

# reSpeaker Flex circular board, read from AEC_MIC_ARRAY_GEO (R005): square, 44.4 mm side.
# Row i = raw mic i = USB channel 3 + i (AUDIO_MGR_OP_CH3..6 = category 1, source 0..3).
FLEX_CIRCULAR_MICS = np.array([
    [0.0222, -0.0222],
    [0.0222, 0.0222],
    [-0.0222, 0.0222],
    [-0.0222, -0.0222],
])


def unit_vectors(az_deg: np.ndarray) -> np.ndarray:
    """(n, 2) unit vectors pointing from the array towards each azimuth."""
    a = np.deg2rad(az_deg)
    return np.stack([np.cos(a), np.sin(a)], axis=-1)


def arrival_delays(mics: np.ndarray, az_deg: np.ndarray, c: float = SPEED_OF_SOUND) -> np.ndarray:
    """(n_az, n_mics) arrival time of a far-field plane wave at each mic, relative to the
    array centre (s). Mics closer to the source hear it earlier (negative delay)."""
    return -(unit_vectors(az_deg) @ mics.T) / c


def steering_vectors(mics: np.ndarray, az_deg: np.ndarray, freqs: np.ndarray,
                     c: float = SPEED_OF_SOUND) -> np.ndarray:
    """(n_az, n_freq, n_mics) phase of the plane wave at each mic: exp(-j*2*pi*f*tau)."""
    tau = arrival_delays(mics, az_deg, c)  # (n_az, n_mics)
    return np.exp(-2j * np.pi * freqs[None, :, None] * tau[:, None, :])


def spatial_alias_hz(mics: np.ndarray, c: float = SPEED_OF_SOUND) -> float:
    """Frequency above which the closest mic pair aliases spatially (d = lambda / 2)."""
    d = min(np.linalg.norm(a - b) for i, a in enumerate(mics) for b in mics[i + 1:])
    return c / (2 * d)
