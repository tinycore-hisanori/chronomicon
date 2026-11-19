"""Build orchestration: converter, glue, cc65 toolchain, link and iNES assembly."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from converter.converter import run_pipeline
from converter.errors import ConversionError

from .config import BuildConfig
from .errors import BuildError
from .glue import write_glue
from .ines import assemble_rom
from .linkmap import find_overflow, parse_ld65_overflow, parse_segment_list
from .tools import ToolPaths, find_tools, run_tool

CHR_SIZE = 8192
_NAMETABLE_RE = re.compile(r"^nametable_(\d+)\.s$")


@dataclass(frozen=True)
class BuildResult:
    rom_path: Path
    map_path: Path
    label_path: Path
    size: int
    crc32: int
    screen_count: int


def _remove_tree(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def _forward_warnings(stderr: str) -> None:
    text = stderr.strip()
    if text:
        print(text, file=sys.stderr)


def _object_plan(config: BuildConfig, assets_dir: Path) -> list[tuple[str, Path]]:
    """Return ``(tag, source)`` pairs in the fixed link order."""
    rt = config.runtime_dir
    plan: list[tuple[str, Path]] = []
    plan += [(f"rt_{p.stem}", p) for p in sorted(rt.glob("*.s"))]
    plan += [(f"rt_{p.stem}", p) for p in sorted(rt.glob("*.c"))]
    plan.append(("assets_data", assets_dir / "assets_data.c"))
    plan.append(("screens", assets_dir / "screens.s"))
    numbered = []
    for p in assets_dir.iterdir():
        m = _NAMETABLE_RE.match(p.name)
        if m:
            numbered.append((int(m.group(1)), p))
    plan += [(f"nametable_{n}", p) for n, p in sorted(numbered)]
    plan += [(f"game_{p.stem}", p) for p in config.game_sources]
    return plan


def _compile(config: BuildConfig, tools: ToolPaths, tag: str, src: Path) -> Path:
    obj_dir = config.obj_dir.resolve()
    rt = str(config.runtime_dir.resolve())
    as_dir = str(config.assets_dir.resolve())
    asm = src
    if src.suffix == ".c":
        asm = obj_dir / f"{tag}.s"
        proc = run_tool(
            [tools.cc65, "-t", "none", "-O", "--cpu", "6502", "-I", rt, "-I", as_dir,
             "-o", asm, src],
            str(src),
        )
        _forward_warnings(proc.stderr)
    obj = obj_dir / f"{tag}.o"
    proc = run_tool(
        [tools.ca65, "--cpu", "6502", "-I", rt, "-o", obj, asm],
        str(asm),
    )
    _forward_warnings(proc.stderr)
    return obj


def _link(config: BuildConfig, tools: ToolPaths, objects: list[Path]) -> Path:
    prg_bin = config.obj_dir.resolve() / "prg.bin"
    argv: list[str] = [str(tools.ld65), "-C", str(config.runtime_dir.resolve() / "nrom.cfg")]
    if config.prg_kb == 16:
        argv += ["-D", "CHRONO_PRG_START=0xC000", "-D", "CHRONO_PRG_SIZE=0x3FFA"]
    argv += [
        "-m", str(config.map_path.resolve()),
        "-Ln", str(config.label_path.resolve()),
        "-o", str(prg_bin),
        *[str(o) for o in objects],
        str(tools.none_lib),
    ]
    try:
        proc = subprocess.run(argv, capture_output=True, check=False)
    except OSError as exc:
        raise BuildError(f"ld65: cannot run {tools.ld65}: {exc}") from exc
    stderr = proc.stderr.decode("utf-8", errors="replace")
    if proc.returncode != 0:
        overflow = None
        try:
            text = config.map_path.read_text(encoding="utf-8", errors="replace")
            overflow = find_overflow(
                parse_segment_list(text), config.prg_start, config.prg_size
            )
        except OSError:
            pass
        if overflow is None:
            overflow = parse_ld65_overflow(stderr)
        if overflow is not None:
            raise BuildError(
                f"PRG overflow: segment {overflow.segment} does not fit in "
                f"{config.prg_kb} KB of PRG, it is {overflow.bytes} bytes too large"
            )
        raise BuildError(f"ld65 failed (exit code {proc.returncode}):\n{stderr.strip()}")
    _forward_warnings(stderr)
    return prg_bin


def build(
    config: BuildConfig,
    tools: ToolPaths | None = None,
    log: Callable[[str], None] = print,
) -> BuildResult:
    """Build ``<build_dir>/<name>.nes``. Raises BuildError on any failure."""
    if tools is None:
        tools = find_tools()
    try:
        _remove_tree(config.assets_dir)
        _remove_tree(config.obj_dir)
        _remove_tree(config.rom_path)
        config.obj_dir.mkdir(parents=True, exist_ok=True)

        try:
            run_pipeline(None, config.manifest_path, config.assets_dir)
        except ConversionError as exc:
            raise BuildError(f"conversion failed: {exc}") from exc

        info = write_glue(config.assets_dir)

        objects = [
            _compile(config, tools, tag, src)
            for tag, src in _object_plan(config, config.assets_dir)
        ]
        prg_bin = _link(config, tools, objects)

        prg = prg_bin.read_bytes()
        if len(prg) != config.prg_kb * 1024:
            raise BuildError(
                f"internal error: prg.bin is {len(prg)} bytes, expected {config.prg_kb * 1024}"
            )
        chr_bin = (config.assets_dir / "chr.bin").read_bytes()
        if len(chr_bin) != CHR_SIZE:
            raise BuildError(f"internal error: chr.bin is {len(chr_bin)} bytes, expected {CHR_SIZE}")

        rom = assemble_rom(prg, chr_bin, config.prg_kb, config.mirroring)
        tmp = config.rom_path.with_name(config.rom_path.name + ".tmp")
        tmp.write_bytes(rom)
        os.replace(tmp, config.rom_path)
    except OSError as exc:
        raise BuildError(f"{exc.filename or config.build_dir}: {exc}") from exc

    crc = zlib.crc32(rom) & 0xFFFFFFFF
    log(f"build/{config.name}.nes: {len(rom)} bytes, crc32={crc:08x}")
    return BuildResult(
        rom_path=config.rom_path,
        map_path=config.map_path,
        label_path=config.label_path,
        size=len(rom),
        crc32=crc,
        screen_count=info.screen_count,
    )
