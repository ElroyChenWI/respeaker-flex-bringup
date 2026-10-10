"""Fair beamformer / post-filter evaluation by digital mixing + shadow filtering.

Record the two components separately at fixed positions (doa_live.py saves 6ch WAVs):
  py -3.11 host/doa_live.py --sec 12 --label speech    # talker only
  py -3.11 host/doa_live.py --sec 12 --label noise     # interferer only (e.g. phone music)

  py -3.11 host/mix_eval.py captures/doa_..._truespeech.wav captures/doa_..._truenoise.wav [--snr 0]

Sound adds linearly in air, so speech + noise summed in the digital domain equals a real
simultaneous recording (up to the mic self-noise being counted twice). Every method computes
its weights / gains on the MIXTURE only; the very same linear weights and time-frequency gains
are then applied to the speech and noise components separately ("shadow filtering"), giving
the true output SNR and speech distortion for linear and non-linear methods alike.

Noise statistics (MVDR covariance, Wiener noise PSD) come from the first half of the
noise-only recording; the mixture uses the second half, so nothing is scored on training data.

Metrics per output
  SNR        speech power / noise power at the output
  SDR(spk)   speech fidelity: output speech component vs the reference-mic speech, after the
             best scalar gain (catches over-suppression a pure SNR number hides)
  STOI       short-time objective intelligibility of the full output vs clean reference speech
             (needs `pip install pystoi`; skipped otherwise)
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


def mean_srp_az(x: np.ndarray) -> float:
    doa = SrpPhat(FLEX_CIRCULAR_MICS, FS)
    m = np.mean([doa.process(x[k:k + 1024]).srp for k in range(0, len(x) - 1024, 512)], axis=0)
    return float(doa.grid[np.argmax(m)])


def db(p: float) -> float:
    return 10 * np.log10(max(p, 1e-30))


def sdr(est: np.ndarray, ref: np.ndarray) -> float:
    """Scale-invariant SDR of est vs ref (dB)."""
    a = np.dot(est, ref) / (np.dot(ref, ref) + 1e-30)
    return db(np.sum((a * ref) ** 2) / (np.sum((est - a * ref) ** 2) + 1e-30))


def save(path: Path, y: np.ndarray) -> None:
    y = y / (np.max(np.abs(y)) + 1e-12) * 0.9
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(FS)
        w.writeframes((y * 32767).astype(np.int16).tobytes())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("speech", type=Path)
    ap.add_argument("noise", type=Path)
    ap.add_argument("--snr", type=float, help="rescale noise to this input SNR at mic0 (dB); default: as recorded")
    ap.add_argument("--skip", type=float, default=0.5, help="seconds trimmed at both ends of each recording")
    args = ap.parse_args()

    sk = int(args.skip * FS)
    s = read_wav(args.speech).astype(np.float64)[sk:-sk, RAW_MIC_CHANNELS]
    n_all = read_wav(args.noise).astype(np.float64)[sk:-sk, RAW_MIC_CHANNELS]
    half = len(n_all) // 2
    n_train, n_test = n_all[:half], n_all[half:]
    L = min(len(s), len(n_test))
    s, n = s[:L], n_test[:L]
    if args.snr is not None:
        n = n * np.sqrt(np.mean(s[:, 0] ** 2) / np.mean(n[:, 0] ** 2) / 10 ** (args.snr / 10))
        n_train = n_train * np.sqrt(np.mean(s[:, 0] ** 2) / np.mean(n_test[:L, 0] ** 2) / 10 ** (args.snr / 10))
    x = s + n

    target_az, interf_az = mean_srp_az(s), mean_srp_az(n_train)
    print(f"talker ~{target_az:.0f} deg (speech-only SRP), interferer ~{interf_az:.0f} deg (noise-only SRP), "
          f"{L / FS:.1f} s mixture, input SNR at mic0 {db(np.mean(s[:, 0] ** 2) / np.mean(n[:, 0] ** 2)):+.1f} dB")

    X, S, N = bf.stft(x), bf.stft(s), bf.stft(n)
    Rn = bf.noise_covariance(bf.stft(n_train))
    d = bf.steering(FLEX_CIRCULAR_MICS, target_az, FS)
    w_mic0 = np.zeros_like(d)
    w_mic0[:, 0] = 1
    w_das = d / d.shape[1]
    w_mvdr = bf.mvdr_weights(Rn, d)

    def run(w, post: bool):
        """Weights (and Wiener gains) decided on the mixture, then shadow-applied."""
        Yx, Ys, Yn = (bf.apply_weights(Z, w) for Z in (X, S, N))
        if post:
            G = np.abs(bf.wiener_postfilter(Yx, bf.output_noise_psd(Rn, w))) / (np.abs(Yx) + 1e-30)
            Yx, Ys, Yn = G * Yx, G * Ys, G * Yn
        return tuple(bf.istft(Z, L) for Z in (Yx, Ys, Yn))

    methods = {
        "mic0 (raw)": (w_mic0, False),
        "mic0 + Wiener": (w_mic0, True),
        "delay-and-sum": (w_das, False),
        "MVDR": (w_mvdr, False),
        "MVDR + Wiener (MWF)": (w_mvdr, True),
    }
    try:
        from pystoi import stoi
    except ImportError:
        stoi = None
        print("(pystoi not installed: STOI skipped - pip install pystoi)")

    # Clean-speech references: mic0 for single-mic methods; for array methods the speech at
    # the array centre (= delay-and-sum of the clean speech), since steering is referenced to
    # the centre - comparing against mic0 would count its sub-sample offset as distortion.
    ref_mic0 = s[:, 0]
    ref_centre = bf.istft(bf.apply_weights(S, w_das), L)
    core = slice(bf.NFFT, L - bf.NFFT)
    stem = args.speech.with_name(args.speech.stem + "_mix")
    print(f"{'method':<22} {'SNR':>7} {'gain':>7} {'SDR(spk)':>9} {'STOI':>6}")
    base = None
    for name, (w, post) in methods.items():
        yx, ys, yn = run(w, post)
        snr = db(np.mean(ys[core] ** 2) / np.mean(yn[core] ** 2))
        base = snr if base is None else base
        ref = ref_mic0 if w is w_mic0 else ref_centre
        st = f"{stoi(ref[core], yx[core], FS, extended=False):6.3f}" if stoi else "   n/a"
        print(f"{name:<22} {snr:6.1f}  {snr - base:+6.1f}  {sdr(ys[core], ref[core]):8.1f}  {st}")
        save(Path(f"{stem}_{name.split()[0].lower().replace('-', '')}{'_wiener' if post else ''}.wav"), yx)
    print("SNR/SDR in dB. gain = SNR improvement over mic0. SDR(spk): higher = less speech distortion.")
    print("XVF3800 cannot be shadow-filtered (closed DSP): compare it by listening, see R009.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
