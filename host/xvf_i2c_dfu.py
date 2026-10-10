"""Flash an XVF3800 firmware image over I2C, through the XIAO ESP32S3 shell.

No USB connection to the XVF3800 and no SafeMode button needed.

  py -3.11 host/xvf_i2c_dfu.py --status                       # read DFU state only
  py -3.11 host/xvf_i2c_dfu.py third_party/reSpeaker_Flex/xmos_firmwares/usb/v1.0.4/respeaker_flex_usb_c16k6ch_v1.0.4.bin

Only the upgrade partition is written; the factory image cannot be overwritten, and an
invalid upgrade image makes the XVF3800 bootloader fall back to the factory image
(XMOS fwk_xvf "DFU operations"). Do not unplug the board while blocks are being sent.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import time
from pathlib import Path

from evk.serial_link import DEFAULT_PORT, EvkError, EvkSerial

BLOCK = 128
STATE_NAMES = {0: "appIDLE", 1: "appDETACH", 2: "dfuIDLE", 3: "dfuDNLOAD-SYNC", 4: "dfuDNBUSY", 5: "dfuDNLOAD-IDLE",
               6: "dfuMANIFEST-SYNC", 7: "dfuMANIFEST", 8: "dfuMANIFEST-WAIT-RESET", 9: "dfuUPLOAD-IDLE", 10: "dfuERROR"}


def kv_of(reply: str) -> dict:
    return dict(t.split("=", 1) for t in reply.split() if "=" in t)


def state_of(reply: str) -> str:
    kv = kv_of(reply)
    return f"{STATE_NAMES.get(int(kv.get('state', -1)), kv.get('state'))} (status={kv.get('status')})"


def send_block(link: EvkSerial, seq: int, chunk: bytes, attempts: int = 6) -> int:
    """Send one block; returns the number of retries used.

    The ESP32 tracks the next expected sequence number, so after a lost line or reply we
    ask it where it is and resend only if the block really was not written (R005).
    """
    line = f"dfu blk {seq} {chunk.hex()} {sum(chunk) & 0xFFFF:04X}"
    for attempt in range(attempts):
        try:
            link.command(line, timeout=5)
            return attempt
        except EvkError as e:
            msg = str(e)
            if "rc=" in msg and "checksum" not in msg and "expected=" not in msg:
                raise  # the XVF3800 itself rejected the block: not a transport problem
        link.drain(0.5)
        nxt = int(kv_of(link.command("dfu status", timeout=10)[0])["next"])
        if nxt == seq + 1:
            return attempt + 1  # it was written; only the reply got lost
        if nxt != seq:
            raise EvkError(f"sequence lost: device expects block {nxt}, host is at {seq}")
    raise EvkError(f"block {seq} failed after {attempts} attempts")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image", nargs="?", type=Path)
    ap.add_argument("--port", default=DEFAULT_PORT)
    ap.add_argument("--status", action="store_true", help="only read the DFU state")
    ap.add_argument("--no-detach", action="store_true", help="do not reboot the XVF3800 after flashing")
    args = ap.parse_args()

    with EvkSerial(args.port) as link:
        print("before:", state_of(link.command("dfu status")[0]))
        if args.status or not args.image:
            return 0

        data = args.image.read_bytes()
        if len(data) % BLOCK:
            print(f"error: image size {len(data)} is not a multiple of {BLOCK}", file=sys.stderr)
            return 2
        nblk = len(data) // BLOCK
        print(f"image: {args.image.name}  {len(data)} bytes  {nblk} blocks  sha256 {hashlib.sha256(data).hexdigest()[:16]}…")

        print("begin:", state_of(link.command("dfu begin")[0]))
        t0 = time.monotonic()
        i = retries = 0
        try:
            for i in range(nblk):
                r = send_block(link, i, data[i * BLOCK:(i + 1) * BLOCK])
                if r:
                    retries += r
                    print(f"\n  block {i}: recovered after {r} retry(s)")
                if i % max(1, nblk // 50) == 0 or i == nblk - 1:
                    el = time.monotonic() - t0
                    eta = el / (i + 1) * (nblk - i - 1)
                    print(f"\r  {100 * (i + 1) / nblk:5.1f}%  block {i + 1}/{nblk}  {el:5.0f}s elapsed  ~{eta:4.0f}s left", end="", flush=True)
            print()
            print("end:", state_of(link.command("dfu end", timeout=30)[0]))
        except (EvkError, KeyboardInterrupt) as e:
            print(f"\nFAILED at block {i}/{nblk}: {e!r} - aborting transfer", file=sys.stderr)
            try:
                link.command("dfu abort")
            except EvkError:
                pass
            print("The old image may be partly overwritten; on reboot the bootloader falls back to the factory image.\n"
                  "You can simply run this tool again.", file=sys.stderr)
            return 1
        print(f"download done in {time.monotonic() - t0:.0f}s, {retries} transport retries")
        if not args.no_detach:
            print("detach:", link.command("dfu detach")[0])
            print("XVF3800 is rebooting into the new image.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except EvkError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
