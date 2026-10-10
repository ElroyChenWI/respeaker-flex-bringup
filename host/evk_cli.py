"""Talk to the XIAO ESP32S3 bring-up shell.

  py -3.11 host/evk_cli.py raw "info"
  py -3.11 host/evk_cli.py get VERSION
  py -3.11 host/evk_cli.py set LED_EFFECT 3
  py -3.11 host/evk_cli.py list [filter]
  py -3.11 host/evk_cli.py doa --watch
  py -3.11 host/evk_cli.py dsp --watch    # XVF3800 DSP health while you talk
  py -3.11 host/evk_cli.py smoke          # B1..B3 gate checks in one go
"""
from __future__ import annotations

import argparse
import math
import sys
import time

from evk import xvf_table
from evk.serial_link import DEFAULT_PORT, EvkError, EvkSerial


def _parse_num(s: str):
    s = s.strip()
    if s.lower().startswith("0x"):
        return int(s, 16)
    return float(s) if any(c in s for c in ".eE") else int(s)


def xvf_get(link: EvkSerial, p: xvf_table.Param):
    if p.access == "wo":
        raise EvkError(f"{p.name} is write-only")
    reply, _ = link.command(f"xr {p.resid} {p.cmdid} {p.nbytes}")
    payload = bytes(int(b, 16) for b in reply.split()[2:])
    return p.decode(payload)


def xvf_set(link: EvkSerial, p: xvf_table.Param, values: list):
    if p.access == "ro":
        raise EvkError(f"{p.name} is read-only")
    data = p.encode(values)
    link.command(f"xw {p.resid} {p.cmdid} " + " ".join(str(b) for b in data))


def dsp_line(link: EvkSerial, table: dict[str, xvf_table.Param]) -> str:
    """One-line XVF3800 DSP health: thread headroom, AGC, speech energy, beam / DoA."""
    g = lambda n: xvf_get(link, table[n])  # noqa: E731
    energy = g("AEC_SPENERGY_VALUES")
    azim = g("AEC_AZIMUTH_VALUES")  # radians: beam1, beam2, free-running, auto-select
    doa, speech = g("DOA_VALUE")
    return (
        f"idle aec={g('AEC_CURRENT_IDLE_TIME')[0]:>7} pp={g('PP_CURRENT_IDLE_TIME')[0]:>7} | "
        f"agc={g('PP_AGCGAIN')[0]:6.2f} | sp_energy_max={max(energy):10.4g} | "
        f"scan={math.degrees(azim[2]) % 360:5.1f} auto={math.degrees(azim[3]) % 360:5.1f} deg | "
        f"doa={doa:3d} speech={speech} | aec_conv={g('AEC_AECCONVERGED')[0]}"
    )


def cmd_smoke(link: EvkSerial) -> int:
    """Stage gates B1-B3. Prints PASS/FAIL per step, returns failure count."""
    fails = 0

    def step(name, fn):
        nonlocal fails
        try:
            print(f"[PASS] {name}: {fn()}")
        except Exception as e:  # noqa: BLE001 - report and keep going
            fails += 1
            print(f"[FAIL] {name}: {e}")

    step("B1 shell", lambda: link.command("info")[0])
    def i2cscan():
        reply, info = link.command("i2cscan")
        if not any("xvf3800" in line for line in info):
            raise EvkError(f"XVF3800 (0x2C) not on bus: {info} {reply}")
        return " | ".join(info + [reply])

    step("B2 i2c scan", i2cscan)
    step("B2 xvf version", lambda: link.command("ver")[0])
    def clkprobe():
        link.command("i2s stop")
        reply, _ = link.command("clkprobe")
        ws = int(reply.split("ws_hz~")[1].split()[0])
        if not 40000 <= ws <= 56000:
            raise EvkError(f"XVF not driving 48 kHz WS: {reply}")
        return reply

    def level():
        reply, _ = link.command("stat 1000", timeout=10)
        rms = float(reply.split("L_rms_dbfs=")[1].split()[0])
        # garbage from clock contention reads about -6 dBFS (R003); real room audio is far lower
        if not -100 < rms < -15:
            raise EvkError(f"L rms {rms} dBFS not audio-like: {reply}")
        return reply

    step("B3 xvf drives clocks", clkprobe)
    step("B3 i2s start (slave)", lambda: link.command("i2s start", timeout=10)[0])
    step("B3 i2s level", level)
    return fails


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", default=DEFAULT_PORT)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_raw = sub.add_parser("raw", help="send a raw shell line")
    p_raw.add_argument("line")
    p_get = sub.add_parser("get", help="read an XVF3800 parameter by name")
    p_get.add_argument("name")
    p_set = sub.add_parser("set", help="write an XVF3800 parameter by name")
    p_set.add_argument("name")
    p_set.add_argument("values", nargs="+")
    p_list = sub.add_parser("list", help="list XVF3800 parameters")
    p_list.add_argument("filter", nargs="?", default="")
    p_doa = sub.add_parser("doa", help="read direction of arrival")
    p_doa.add_argument("--watch", action="store_true")
    p_doa.add_argument("--interval", type=float, default=0.2)
    p_dsp = sub.add_parser("dsp", help="XVF3800 DSP health line (speech energy, beams, DoA)")
    p_dsp.add_argument("--watch", action="store_true")
    p_dsp.add_argument("--interval", type=float, default=0.3)
    sub.add_parser("smoke", help="run B1-B3 bring-up checks")
    args = ap.parse_args()

    if args.cmd == "list":
        for p in xvf_table.load().values():
            if args.filter.upper() in p.name:
                print(f"{p.name:<34} resid={p.resid:<3} cmd={p.cmdid:<3} n={p.count:<3} {p.type:<8} {p.access}  {p.desc[:70]}")
        return 0

    try:
        with EvkSerial(args.port) as link:
            if args.cmd == "raw":
                reply, info = link.command(args.line, timeout=30)
                print("\n".join(info + [reply]))
            elif args.cmd in ("get", "set"):
                table = xvf_table.load()
                name = args.name.upper()
                if name not in table:
                    print(f"unknown parameter {name}; try: evk_cli.py list {name[:4]}")
                    return 2
                if args.cmd == "get":
                    print(f"{name}: {xvf_get(link, table[name])}")
                else:
                    xvf_set(link, table[name], [_parse_num(v) for v in args.values])
                    print(f"{name} <- {args.values}")
            elif args.cmd == "doa":
                while True:
                    print(link.command("doa")[0], flush=True)
                    if not args.watch:
                        break
                    time.sleep(args.interval)
            elif args.cmd == "dsp":
                table = xvf_table.load()
                while True:
                    print(dsp_line(link, table), flush=True)
                    if not args.watch:
                        break
                    time.sleep(args.interval)
            elif args.cmd == "smoke":
                fails = cmd_smoke(link)
                print("SMOKE", "PASS" if fails == 0 else f"FAIL ({fails})")
                return 1 if fails else 0
    except (EvkError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
