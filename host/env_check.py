"""B0: check that the EVK and the toolchain are visible from this PC.

  py -3.11 host/env_check.py
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from serial.tools import list_ports

KNOWN_USB = {
    (0x303A, 0x1001): "XIAO ESP32S3 USB-Serial/JTAG (bring-up shell / esptool)",
    (0x2886, 0x001A): "XVF3800 reSpeaker (USB firmware / DFU)",
}
HOME = Path(os.environ.get("USERPROFILE", Path.home()))
TOOLS = {
    "git": shutil.which("git"),
    "pio": str(p) if (p := HOME / ".platformio/penv/Scripts/pio.exe").exists() else None,
    "esptool.py": str(p) if (p := HOME / ".platformio/packages/tool-esptoolpy/esptool.py").exists() else None,
    "dfu-util": shutil.which("dfu-util"),
}


def main() -> int:
    print("== serial ports ==")
    found_xiao = False
    for port in list_ports.comports():
        tag = KNOWN_USB.get((port.vid, port.pid), "")
        found_xiao |= (port.vid, port.pid) == (0x303A, 0x1001)
        vidpid = f"{port.vid:04X}:{port.pid:04X}" if port.vid is not None else "----:----"
        print(f"  {port.device:<6} {vidpid}  {port.description}  {tag}")

    print("== XVF3800 on USB (only with USB firmware, via its own USB-C) ==")
    try:
        import libusb_package  # noqa: F401
        import usb.core  # noqa: F401

        devs = list(libusb_package.find(find_all=True, idVendor=0x2886) or [])
        for d in devs:
            print(f"  2886:{d.idProduct:04X}  {KNOWN_USB.get((0x2886, d.idProduct), '')}")
        if not devs:
            print("  none (expected while XVF runs the I2S image)")
    except ImportError:
        print("  skipped (pip install pyusb libusb-package)")

    print("== tools ==")
    for name, path in TOOLS.items():
        print(f"  {name:<10} {path or 'MISSING'}")

    vendor = Path(__file__).resolve().parents[1] / "third_party/reSpeaker_Flex"
    print(f"== vendor ==\n  reSpeaker_Flex: {'ok' if vendor.exists() else 'MISSING (scripts/fetch_vendor.ps1)'}")

    print("B0", "PASS" if found_xiao else "FAIL (XIAO 303A:1001 not found)")
    return 0 if found_xiao else 1


if __name__ == "__main__":
    sys.exit(main())
