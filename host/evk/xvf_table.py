"""XVF3800 control-command table, read from Seeed's xvf_host.py.

The table is parsed (not imported) from third_party/reSpeaker_Flex, so it needs no
pyusb and always matches the vendored firmware release. Run scripts/fetch_vendor.ps1 first.
"""
from __future__ import annotations

import ast
import struct
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
VENDOR_XVF_HOST = REPO_ROOT / "third_party" / "reSpeaker_Flex" / "python_control" / "xvf_host.py"

# element size (bytes) and struct code per type name used in xvf_host.py
_TYPES = {
    "uint8": (1, "B"),
    "char": (1, "s"),
    "uint16": (2, "H"),
    "int32": (4, "i"),
    "uint32": (4, "I"),
    "float": (4, "f"),
    "radians": (4, "f"),
}


@dataclass(frozen=True)
class Param:
    name: str
    resid: int
    cmdid: int
    count: int
    access: str  # ro / wo / rw
    type: str
    desc: str

    @property
    def nbytes(self) -> int:
        return self.count * _TYPES[self.type][0]

    def decode(self, payload: bytes):
        if self.type == "char":
            return payload.rstrip(b"\x00").decode("utf-8", errors="ignore")
        return struct.unpack("<" + _TYPES[self.type][1] * self.count, payload[: self.nbytes])

    def encode(self, values: list) -> bytes:
        if len(values) != self.count:
            raise ValueError(f"{self.name} takes {self.count} value(s), got {len(values)}")
        code = _TYPES[self.type][1]
        if code == "s":
            return bytes(int(v) for v in values)
        if code == "f":
            return struct.pack("<" + "f" * self.count, *(float(v) for v in values))
        return struct.pack("<" + code * self.count, *(int(v) for v in values))


def load(path: Path = VENDOR_XVF_HOST) -> dict[str, Param]:
    if not path.exists():
        raise FileNotFoundError(f"{path} missing - run scripts\\fetch_vendor.ps1")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "PARAMETERS" for t in node.targets
        ):
            raw = ast.literal_eval(node.value)
            # tuple order in xvf_host.py: resid, cmdid, count, access, type, description
            return {name: Param(name, *fields) for name, fields in raw.items()}
    raise ValueError(f"PARAMETERS table not found in {path}")
