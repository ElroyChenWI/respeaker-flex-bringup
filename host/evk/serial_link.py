"""Serial link to the XIAO ESP32S3 bring-up shell (firmware/xiao_esp32s3)."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass

import serial

DEFAULT_PORT = "COM8"
_REC_HEADER = re.compile(rb"REC rate=(\d+) ch=(\d+) bits=(\d+) bytes=(\d+)")


class EvkError(RuntimeError):
    pass


@dataclass
class Recording:
    rate: int
    channels: int
    bits: int
    pcm: bytes
    trailer: str  # "OK rec frames=... padded=..."


class EvkSerial:
    def __init__(self, port: str = DEFAULT_PORT, timeout: float = 2.0):
        s = serial.Serial()
        s.port = port
        s.baudrate = 115200  # ignored by USB-Serial/JTAG
        s.timeout = timeout
        # Do not toggle DTR/RTS: on the ESP32-S3 USB-Serial/JTAG that resets the chip.
        s.dtr = False
        s.rts = False
        s.open()
        self._s = s
        self.drain()

    def close(self) -> None:
        self._s.close()

    def __enter__(self) -> "EvkSerial":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def drain(self, settle: float = 0.2) -> bytes:
        """Discard pending input (boot banner, leftovers)."""
        time.sleep(settle)
        return self._s.read(self._s.in_waiting or 0)

    def _readline(self, deadline: float) -> str:
        while time.monotonic() < deadline:
            raw = self._s.readline()
            if raw:
                return raw.decode("utf-8", errors="replace").rstrip("\r\n")
        raise EvkError("timeout waiting for reply")

    def command(self, line: str, timeout: float = 5.0) -> tuple[str, list[str]]:
        """Send one command. Returns (final OK line, '#' info lines). Raises on ERR."""
        self._s.write((line.strip() + "\n").encode())
        deadline = time.monotonic() + timeout
        info: list[str] = []
        while True:
            reply = self._readline(deadline)
            if reply.startswith("OK"):
                return reply, info
            if reply.startswith("ERR"):
                raise EvkError(f"{line!r}: {reply}")
            if reply:
                info.append(reply)

    def record(self, ms: int, bits: int = 16) -> Recording:
        self._s.write(f"rec {ms} {bits}\n".encode())
        deadline = time.monotonic() + 5.0
        while True:
            reply = self._readline(deadline)
            if reply.startswith("ERR"):
                raise EvkError(reply)
            m = _REC_HEADER.match(reply.encode())
            if m:
                break
        rate, ch, bits_, nbytes = (int(x) for x in m.groups())
        pcm = bytearray()
        deadline = time.monotonic() + ms / 1000 + 10.0
        while len(pcm) < nbytes:
            if time.monotonic() > deadline:
                raise EvkError(f"rec stalled at {len(pcm)}/{nbytes} bytes")
            pcm += self._s.read(min(65536, nbytes - len(pcm)))
        trailer = ""
        end = time.monotonic() + 5.0
        while not trailer.startswith("OK rec"):
            trailer = self._readline(end)
        return Recording(rate, ch, bits_, bytes(pcm), trailer)
