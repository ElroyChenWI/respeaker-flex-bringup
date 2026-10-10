"""Local web GUI for the reSpeaker Flex EVK (stdlib only).

  py -3.11 host/evk_gui.py            -> http://127.0.0.1:8765

One process owns the XIAO serial port (auto-detected, or --port). A poller thread refreshes levels + XVF3800 DSP state;
HTTP handlers share the serial link through a lock (recording pauses polling).
"""
from __future__ import annotations

import argparse
import json
import math
import threading
import time
import traceback
import wave
from datetime import datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

import numpy as np

from evk import xvf_table
from evk.serial_link import DEFAULT_PORT, EvkError, EvkSerial
from evk_cli import xvf_get, xvf_set

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
CAPTURES = REPO_ROOT / "captures"
STATIC = HERE / "gui"


class Evk:
    def __init__(self, port: str):
        self.port = port
        self.table = xvf_table.load()
        self.lock = threading.Lock()
        self.link: EvkSerial | None = None
        self.status: dict = {"connected": False}
        self.busy = ""  # non-empty while a long operation (recording) holds the link
        self.poll_enabled = True

    # --- connection -------------------------------------------------------
    def connect(self) -> None:
        with self.lock:
            if self.link:
                return
            self.link = EvkSerial(self.port)
            reply, info = self.link.command("info")
            self.link.command("i2s start", timeout=10)
            ver = xvf_get(self.link, self.table["VERSION"])
            bld = xvf_get(self.link, self.table["BLD_MSG"])
            self.status.update(connected=True, port=self.link.port, info=info + [reply], xvf_version=".".join(map(str, ver)), xvf_build=bld)

    def drop(self, err: Exception) -> None:
        if self.link:
            try:
                self.link.close()
            except OSError:
                pass
        self.link = None
        self.status = {"connected": False, "error": str(err)}

    # --- polling ----------------------------------------------------------
    def _parse_stat(self, reply: str) -> dict:
        kv = dict(tok.split("=", 1) for tok in reply.split()[2:] if "=" in tok)
        return {k: float(v) for k, v in kv.items()}

    def poll_once(self) -> None:
        g = lambda n: xvf_get(self.link, self.table[n])  # noqa: E731
        with self.lock:
            stat = self._parse_stat(self.link.command("stat 100", timeout=5)[0])
            azim = g("AEC_AZIMUTH_VALUES")
            energy = g("AEC_SPENERGY_VALUES")
            doa, speech = g("DOA_VALUE")
            snap = {
                "level": {"L": stat.get("L_rms_dbfs"), "R": stat.get("R_rms_dbfs"),
                          "Lpk": stat.get("L_peak_dbfs"), "Rpk": stat.get("R_peak_dbfs")},
                "azimuth_deg": [round(math.degrees(a) % 360, 1) for a in azim],
                "speech_energy": [float(e) for e in energy],
                "doa": doa, "speech": speech,
                "agc_gain": g("PP_AGCGAIN")[0],
                "aec_converged": g("AEC_AECCONVERGED")[0],
                "idle": {"aec": g("AEC_CURRENT_IDLE_TIME")[0], "pp": g("PP_CURRENT_IDLE_TIME")[0],
                         "aec_min": g("AEC_MIN_IDLE_TIME")[0], "pp_min": g("PP_MIN_IDLE_TIME")[0]},
                "fixed_beams": g("AEC_FIXEDBEAMSONOFF")[0],
                "op_l": list(g("AUDIO_MGR_OP_L")), "op_r": list(g("AUDIO_MGR_OP_R")),
                "t": time.time(),
            }
        self.status.update(snap)

    def poller(self, interval: float) -> None:
        while True:
            try:
                if not self.link:
                    self.connect()
                if self.poll_enabled and not self.busy:
                    self.poll_once()
            except (EvkError, OSError) as e:
                self.drop(e)
                time.sleep(2)
            time.sleep(interval)

    # --- actions ----------------------------------------------------------
    def record(self, sec: float, bits: int) -> dict:
        sec = max(0.5, min(sec, 120.0))
        self.busy = f"recording {sec:.0f}s"
        try:
            with self.lock:
                rec = self.link.record(int(sec * 1000), bits)
        finally:
            self.busy = ""
        CAPTURES.mkdir(exist_ok=True)
        name = f"rec_{datetime.now():%Y%m%d_%H%M%S}.wav"
        with wave.open(str(CAPTURES / name), "wb") as w:
            w.setnchannels(rec.channels)
            w.setsampwidth(rec.bits // 8)
            w.setframerate(rec.rate)
            w.writeframes(rec.pcm)
        dtype, fs = (np.int16, 32768.0) if rec.bits == 16 else (np.int32, 2**31)
        x = np.frombuffer(rec.pcm, dtype).reshape(-1, rec.channels).astype(np.float64) / fs
        rms = [round(20 * math.log10(float(np.sqrt(np.mean(x[:, c] ** 2))) + 1e-12), 1) for c in range(rec.channels)]
        return {"file": name, "rate": rec.rate, "bits": rec.bits, "seconds": sec, "rms_dbfs": rms, "trailer": rec.trailer}

    def param_get(self, name: str):
        p = self.table[name]
        with self.lock:
            return xvf_get(self.link, p)

    def param_set(self, name: str, values: list):
        p = self.table[name]
        with self.lock:
            xvf_set(self.link, p, values)
            return xvf_get(self.link, p) if p.access == "rw" else None


class Handler(SimpleHTTPRequestHandler):
    evk: Evk = None  # set in main

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(STATIC), **kw)

    def log_message(self, fmt, *args):  # keep the console quiet
        pass

    def _json(self, obj, code=HTTPStatus.OK):
        body = json.dumps(obj, default=lambda o: list(o) if isinstance(o, tuple) else str(o)).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        path = urlparse(self.path).path
        evk = self.evk
        if path == "/api/status":
            return self._json({**evk.status, "busy": evk.busy, "poll": evk.poll_enabled})
        if path == "/api/params":
            return self._json([{"name": p.name, "resid": p.resid, "cmd": p.cmdid, "count": p.count,
                                "type": p.type, "access": p.access, "desc": p.desc} for p in evk.table.values()])
        if path == "/api/recordings":
            files = sorted(CAPTURES.glob("*.wav"), key=lambda f: f.stat().st_mtime, reverse=True)[:30]
            return self._json([{"file": f.name, "kb": f.stat().st_size // 1024,
                                "mtime": datetime.fromtimestamp(f.stat().st_mtime).strftime("%m-%d %H:%M:%S")} for f in files])
        if path.startswith("/captures/"):
            f = (CAPTURES / unquote(path[len("/captures/"):])).resolve()
            if f.parent != CAPTURES.resolve() or not f.exists() or f.suffix != ".wav":
                return self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            data = f.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return None
        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        evk = self.evk
        try:
            if not evk.link:
                return self._json({"error": "device not connected"}, HTTPStatus.SERVICE_UNAVAILABLE)
            body = self._body()
            if path == "/api/record":
                return self._json(evk.record(float(body.get("sec", 5)), int(body.get("bits", 16))))
            if path == "/api/get":
                return self._json({"name": body["name"], "value": evk.param_get(body["name"])})
            if path == "/api/set":
                return self._json({"name": body["name"], "value": evk.param_set(body["name"], body["values"])})
            if path == "/api/poll":
                evk.poll_enabled = bool(body.get("enabled", True))
                return self._json({"poll": evk.poll_enabled})
            return self._json({"error": "unknown endpoint"}, HTTPStatus.NOT_FOUND)
        except KeyError as e:
            return self._json({"error": f"unknown parameter {e}"}, HTTPStatus.BAD_REQUEST)
        except (EvkError, ValueError) as e:
            return self._json({"error": str(e)}, HTTPStatus.BAD_REQUEST)
        except OSError as e:
            evk.drop(e)
            return self._json({"error": str(e)}, HTTPStatus.SERVICE_UNAVAILABLE)
        except Exception as e:  # noqa: BLE001 - surface unexpected errors to the UI
            traceback.print_exc()
            return self._json({"error": repr(e)}, HTTPStatus.INTERNAL_SERVER_ERROR)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", default=DEFAULT_PORT)
    ap.add_argument("--http", type=int, default=8765)
    ap.add_argument("--interval", type=float, default=0.15)
    args = ap.parse_args()

    evk = Evk(args.port)
    Handler.evk = evk
    threading.Thread(target=evk.poller, args=(args.interval,), daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", args.http), Handler)
    print(f"EVK GUI on http://127.0.0.1:{args.http}  (serial {args.port})", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
