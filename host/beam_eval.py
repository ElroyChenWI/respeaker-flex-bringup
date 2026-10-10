"""Evaluate own beamformers on a real 6ch recording against a single mic and the XVF3800.

Recording protocol (doa_live.py saves the 6ch WAV):
  1. put a noise source (phone playing music) on one side of the board
  2. first --noise-sec seconds: noise only
  3. then talk from another side for the rest, noise keeps playing

  py -3.11 host/doa_live.py --sec 20 --label beam      # record
  py -3.11 host/beam_eval.py captures/doa_..._truebeam.wav

Directions are found automatically with SRP-PHAT: the interferer from the noise-only part,
the talker from the speech-part SRP map minus the noise-part map (or pass --target-az).
MVDR uses the noise-only part as its noise covariance.

Metric: estimated SNR = (P_speech_part - P_noise_part) / P_noise_part per output, assuming the
noise is stationary. XVF outputs include AGC and noise suppression, so their numbers are
indicative only (AGC gain can differ between the two parts).
"""
from __future__ import annotations

import argparse
import sys
import wave
from pathlib import Path

import numpy as np

from algo import beamformer as bf
from algo.array import FLEX_CIRCULAR_MICS
from algo.sources import FS, RAW_MIC_CHANNELS, read_wav
from algo.srp_phat import SrpPhat


def srp_map(x: np.ndarray) -> np.ndarray:
    doa = SrpPhat(FLEX_CIRCULAR_MICS, FS)
    maps = [doa.process(x[k:k + 1024]).srp for k in range(0, len(x) - 1024, 512)]
    return np.mean(maps, axis=0), doa.grid


def est_snr_db(y: np.ndarray, noise: slice, speech: slice) -> float:
    pn = np.mean(y[noise] ** 2)
    pm = np.mean(y[speech] ** 2)
    return 10 * np.log10(max(pm - pn, 1e-20) / max(pn, 1e-20))


def save(path: Path, y: np.ndarray) -> None:
    y = y / (np.max(np.abs(y)) + 1e-12) * 0.9
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(FS)
        w.writeframes((y * 32767).astype(np.int16).tobytes())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("wav", type=Path)
    ap.add_argument("--noise-sec", type=float, default=5.0)
    ap.add_argument("--skip-sec", type=float, default=0.5, help="ignore this much at each part boundary")
    ap.add_argument("--target-az", type=float, help="talker azimuth (deg); default: estimated")
    args = ap.parse_args()

    x6 = read_wav(args.wav).astype(np.float64)
    mics = x6[:, RAW_MIC_CHANNELS]
    nn = int(args.noise_sec * FS)
    sk = int(args.skip_sec * FS)
    noise_part, speech_part = slice(sk, nn - sk), slice(nn + sk, len(x6) - sk)

    m_noise, grid = srp_map(mics[noise_part])
    m_speech, _ = srp_map(mics[speech_part])
    interf_az = float(grid[np.argmax(m_noise)])
    target_az = args.target_az if args.target_az is not None else float(grid[np.argmax(m_speech - m_noise)])
    print(f"interferer ~{interf_az:.0f} deg (noise-only part), talker ~{target_az:.0f} deg"
          f"{' (given)' if args.target_az is not None else ' (speech map - noise map)'}")

    X = bf.stft(mics)
    d = bf.steering(FLEX_CIRCULAR_MICS, target_az, FS)
    frames_noise = slice(noise_part.start // bf.HOP, (noise_part.stop - bf.NFFT) // bf.HOP)
    w_mvdr = bf.mvdr_weights(bf.noise_covariance(X[frames_noise]), d)
    outputs = {  # name: (file tag, signal)
        "mic0 (raw)": ("mic0", mics[:, 0]),
        "delay-and-sum": ("das", bf.istft(bf.delay_and_sum(X, d), len(mics))),
        "MVDR": ("mvdr", bf.istft(bf.apply_weights(X, w_mvdr), len(mics))),
        "XVF ch1 (processed L)": ("xvf_ch1", x6[:, 0]),
        "XVF ch2 (ASR beam)": ("xvf_ch2", x6[:, 1]),
    }

    base = est_snr_db(outputs["mic0 (raw)"][1], noise_part, speech_part)
    stem = args.wav.with_suffix("")
    print(f"{'output':<24} {'est. SNR':>9} {'vs mic0':>8}   file")
    for name, (tag, y) in outputs.items():
        snr = est_snr_db(y, noise_part, speech_part)
        out = Path(f"{stem}_{tag}.wav")
        save(out, y)
        print(f"{name:<24} {snr:8.1f} dB {snr - base:+7.1f} dB   {out.name}")

    pattern = bf.beam_pattern(w_mvdr, FLEX_CIRCULAR_MICS, FS, np.array([target_az, interf_az]))
    band = (np.fft.rfftfreq(bf.NFFT, 1 / FS) > 300) & (np.fft.rfftfreq(bf.NFFT, 1 / FS) < 3800)
    null = 20 * np.log10(np.mean(pattern[1, band]) / np.mean(pattern[0, band]))
    print(f"MVDR response towards the interferer vs talker (300-3800 Hz): {null:.1f} dB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
