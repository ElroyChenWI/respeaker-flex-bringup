"""Audio and control sources for the XVF3800 USB 6ch firmware (ua-io16-6ch).

Channel map (AUDIO_MGR_OP_* defaults, R005):
  0, 1  processed outputs (L = user-selected output, R = ASR beam)
  2..5  raw mics 0..3 (category 1: no gain, no delay), same order as AEC_MIC_ARRAY_GEO
"""
from __future__ import annotations

import contextlib
import io
import math
import queue
import sys
import wave
from pathlib import Path

import numpy as np

FS = 16000
RAW_MIC_CHANNELS = slice(2, 6)
REPO_ROOT = Path(__file__).resolve().parents[2]
VENDOR_PY = REPO_ROOT / "third_party" / "reSpeaker_Flex" / "python_control"


def find_input_device() -> int:
    """The XVF3800 6-channel input on the WDM-KS host API (native 16 kHz, no resampling)."""
    import sounddevice as sd

    for i, d in enumerate(sd.query_devices()):
        api = sd.query_hostapis(d["hostapi"])["name"]
        if "XVF3800" in d["name"] and d["max_input_channels"] == 6 and "WDM-KS" in api:
            return i
    raise RuntimeError("XVF3800 6ch input not found - is the USB 6ch firmware running and the core-board USB-C connected?")


class LiveCapture:
    """Streams (block, 6) float32 frames from the XVF3800 into a queue."""

    def __init__(self, block: int = 512, device: int | None = None):
        import sounddevice as sd

        self.q: queue.Queue[np.ndarray] = queue.Queue(maxsize=200)
        self.overflows = 0

        def cb(indata, frames, t, status):
            if status.input_overflow:
                self.overflows += 1
            try:
                self.q.put_nowait(indata.astype(np.float32) / 2**31)
            except queue.Full:
                self.overflows += 1

        self.stream = sd.InputStream(samplerate=FS, channels=6, dtype="int32", blocksize=block,
                                     device=find_input_device() if device is None else device, callback=cb)

    def __enter__(self):
        self.stream.start()
        return self

    def __exit__(self, *exc):
        self.stream.stop()
        self.stream.close()


def read_wav(path: Path) -> np.ndarray:
    """(n, ch) float32 from a 16/32-bit PCM WAV."""
    with wave.open(str(path), "rb") as w:
        width, ch, n = w.getsampwidth(), w.getnchannels(), w.getnframes()
        raw = w.readframes(n)
    dtype, scale = {2: (np.int16, 2**15), 4: (np.int32, 2**31)}[width]
    return np.frombuffer(raw, dtype).reshape(-1, ch).astype(np.float32) / scale


class XvfUsb:
    """Read XVF3800 parameters over the USB control interface (vendor xvf_host.py)."""

    def __init__(self):
        sys.path.insert(0, str(VENDOR_PY))
        import xvf_host  # noqa: E402  (vendored, fetched by scripts/fetch_vendor.ps1)

        self.dev = xvf_host.find()
        if self.dev is None:
            raise RuntimeError("XVF3800 USB control interface (VID 0x2886) not found")

    def read(self, name: str):
        with contextlib.redirect_stdout(io.StringIO()):  # xvf_host prints every transfer
            return self.dev.read(name)

    def doa(self) -> tuple[int, int]:
        """(DOA_VALUE degrees, speech flag)."""
        deg, speech = self.read("DOA_VALUE")
        return int(deg), int(speech)

    def auto_beam_deg(self) -> float:
        return math.degrees(self.read("AEC_AZIMUTH_VALUES")[3]) % 360

    def close(self):
        self.dev.close()
