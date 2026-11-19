"""Tool discovery and subprocess runner for the cc65 toolchain.

Nothing is ever downloaded or installed: missing tools are reported.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence

from builder.errors import BuildError

EXPECTED_VERSION = "2.19"
TOOL_NAMES = ("cc65", "ca65", "ld65")


@dataclass(frozen=True)
class ToolPaths:
    """Absolute paths of the cc65 tools and the cc65 library directory."""

    cc65: Path
    ca65: Path
    ld65: Path
    lib_dir: Path

    @property
    def none_lib(self) -> Path:
        return self.lib_dir / "none.lib"


def _version_of(cc65: Path) -> str:
    """Return the text printed by ``cc65 --version`` ('' if it cannot be run)."""
    try:
        proc = subprocess.run(
            [str(cc65), "--version"],
            capture_output=True,
            check=False,
        )
    except OSError:
        return ""
    out = proc.stdout + b"\n" + proc.stderr
    return out.decode("utf-8", errors="replace").strip()


def find_tools(
    which: Callable[[str], str | None] = shutil.which,
    environ: Mapping[str, str] = os.environ,
) -> ToolPaths:
    """Locate cc65, ca65, ld65 and ``none.lib``; raise BuildError if absent."""
    found: dict[str, Path] = {}
    for name in TOOL_NAMES:
        path = which(name)
        if not path:
            raise BuildError(
                f"required tool '{name}' was not found on PATH; install cc65 "
                f"{EXPECTED_VERSION} and add its bin directory to PATH "
                "(this tool never installs anything)"
            )
        found[name] = Path(path)

    home = environ.get("CC65_HOME")
    if home:
        lib_dir = Path(home) / "lib"
    else:
        lib_dir = found["cc65"].resolve().parent.parent / "lib"
    none_lib = lib_dir / "none.lib"
    if not none_lib.is_file():
        raise BuildError(
            f"cc65 library 'none.lib' was not found at {none_lib}; "
            "set CC65_HOME to your cc65 directory (nothing is installed automatically)"
        )

    version_text = _version_of(found["cc65"])
    if EXPECTED_VERSION not in version_text.split():
        # "cc65 V2.19 - Git ..." -> compare the version token itself.
        tokens = [t.lstrip("Vv").rstrip(",;") for t in version_text.split()]
        if not any(t == EXPECTED_VERSION for t in tokens):
            print(
                f"warning: expected cc65 {EXPECTED_VERSION}, found "
                f"'{version_text or 'unknown version'}'; continuing",
                file=sys.stderr,
            )

    return ToolPaths(
        cc65=found["cc65"],
        ca65=found["ca65"],
        ld65=found["ld65"],
        lib_dir=lib_dir,
    )


def run_tool(
    argv: Sequence[str], what: str
) -> subprocess.CompletedProcess[str]:
    """Run a tool without a shell; raise BuildError on a non-zero exit.

    ``what`` names the file or step being processed (used in the error).
    """
    args = [str(a) for a in argv]
    tool = Path(args[0]).stem if args else "tool"
    try:
        proc = subprocess.run(args, capture_output=True, check=False)
    except OSError as exc:
        raise BuildError(f"{tool}: cannot run {args[0]} for {what}: {exc}") from exc
    stdout = proc.stdout.decode("utf-8", errors="replace")
    stderr = proc.stderr.decode("utf-8", errors="replace")
    if proc.returncode != 0:
        raise BuildError(
            f"{tool} failed (exit code {proc.returncode}) on {what}:\n{stderr.strip()}"
        )
    return subprocess.CompletedProcess(args, proc.returncode, stdout, stderr)
