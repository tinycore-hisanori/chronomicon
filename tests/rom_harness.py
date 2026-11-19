"""Python side of the tinynes ROM test harness (drives tests/node/rom_server.js)."""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from builder.linkmap import parse_labels

SERVER_JS = Path(__file__).resolve().parent / "node" / "rom_server.js"

_NODE_MISSING = "Node.js not found on PATH; the ROM tests need Node (nothing is installed automatically)"


def need_node() -> str:
    """Return the path of ``node``; skip (or fail with CHRONO_REQUIRE_TOOLCHAIN=1) if missing."""
    node = shutil.which("node")
    if node:
        return node
    if os.environ.get("CHRONO_REQUIRE_TOOLCHAIN") == "1":
        pytest.fail(_NODE_MISSING)
    pytest.skip(_NODE_MISSING)
    raise AssertionError("unreachable")  # pragma: no cover


@dataclass
class StepResult:
    """Result of one step of a ``run`` request."""

    reads: dict[str, bytes] = field(default_factory=dict)
    snap: dict[str, bytes] = field(default_factory=dict)
    ppu_data_per_frame: list[int] | None = None
    io: list[list[int]] | None = None
    apu: list[list[int]] | None = None


def read_labels(lbl_path: str | os.PathLike[str]) -> dict[str, int]:
    """Parse an ld65 ``-Ln`` label file into ``{name: address}``."""
    return parse_labels(Path(lbl_path).read_text(encoding="utf-8"))


def b64(data: bytes) -> str:
    """Base64-encode bytes for a ``writes`` entry."""
    return base64.b64encode(data).decode("ascii")


class RomRunner:
    """One persistent Node process running one ROM."""

    def __init__(self, rom: bytes | str | os.PathLike[str]) -> None:
        self._rom = rom if isinstance(rom, (bytes, bytearray)) else Path(rom).read_bytes()
        self._proc: subprocess.Popen[str] | None = None
        self._next_id = 0

    def __enter__(self) -> "RomRunner":
        node = need_node()
        self._proc = subprocess.Popen(
            [node, str(SERVER_JS)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        try:
            self._request({"op": "load", "rom": base64.b64encode(bytes(self._rom)).decode("ascii")})
        except BaseException:
            self.close()
            raise
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None:
            return
        try:
            if proc.stdin:
                proc.stdin.close()
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
            proc.wait()
        finally:
            if proc.stdout:
                proc.stdout.close()

    def _request(self, req: dict[str, Any]) -> dict[str, Any]:
        proc = self._proc
        if proc is None or proc.stdin is None or proc.stdout is None:
            raise RuntimeError("RomRunner is not open")
        self._next_id += 1
        req = {"id": self._next_id, **req}
        proc.stdin.write(json.dumps(req) + "\n")
        proc.stdin.flush()
        line = proc.stdout.readline()
        if not line:
            raise RuntimeError("rom_server.js exited without a response")
        resp = json.loads(line)
        if not resp.get("ok"):
            raise RuntimeError(resp.get("error", "unknown rom_server.js error"))
        return resp

    def run(self, steps: list[dict[str, Any]], trace: dict[str, bool] | None = None) -> list[StepResult]:
        req: dict[str, Any] = {"op": "run", "steps": steps}
        if trace:
            req["trace"] = trace
        resp = self._request(req)
        out: list[StepResult] = []
        for s in resp["steps"]:
            out.append(
                StepResult(
                    reads={k: base64.b64decode(v) for k, v in s.get("reads", {}).items()},
                    snap={k: base64.b64decode(v) for k, v in s.get("snap", {}).items()},
                    ppu_data_per_frame=s.get("ppu_data_per_frame"),
                    io=s.get("io"),
                    apu=s.get("apu"),
                )
            )
        return out
