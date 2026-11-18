"""Unit tests for converter.converter (convert, run_pipeline, main)."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from converter import emitter
from converter.converter import convert, main, run_pipeline
from converter.errors import ConversionError
from converter.models import ImageBank, Tilemap
from tests.pyxres_writer import write_pyxres

REPO_ROOT = Path(__file__).resolve().parent.parent
BANK = 64


def _bank(sprite_color: int = 5) -> ImageBank:
    rows = [[0] * BANK for _ in range(BANK)]
    for y in range(8):  # BG tile (0, 0): colors 0..3
        for x in range(8):
            rows[y][x] = (x + y) % 4
    for y in range(16, 32):  # 8x16 sprite at u=0, v=16
        for x in range(8):
            rows[y][x] = sprite_color if (x + y) % 2 else 0
    return ImageBank(BANK, BANK, tuple(tuple(r) for r in rows))


def _tilemap() -> Tilemap:
    row = tuple((0, 0) for _ in range(32))
    return Tilemap(32, 30, 0, tuple(row for _ in range(30)))


def _manifest(**overrides) -> dict:
    data = {
        "pyxres_files": ["game.pyxres"],
        "nes_colors": {str(i): 0x0F + i for i in range(16)},
        "bg_palettes": {"bg0": [0, 1, 2, 3]},
        "sprite_palettes": {"sp0": [0, 5, 6, 7]},
        "bg_palette_regions": [
            {"image_bank": 0, "u": 0, "v": 0, "w": 64, "h": 64, "palette": "bg0"}
        ],
        "sprites": [
            {"name": "hero", "image_bank": 0, "u": 0, "v": 16, "w": 8, "h": 16, "palette": "sp0"}
        ],
        "screens": [
            {"tilemap": 0, "x": 0, "y": 0, "count": 1, "hud_tilemap": 0, "hud_x": 0, "hud_y": 0}
        ],
    }
    data.update(overrides)
    return data


@pytest.fixture
def scene(tmp_path: Path):
    """Return (manifest_path, out_dir) for a valid one-screen scene."""
    write_pyxres(tmp_path / "game.pyxres", [_bank()], [_tilemap()])
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(_manifest()), encoding="utf-8")
    return manifest, tmp_path / "out"


def _snapshot(directory: Path) -> dict[str, tuple[bytes, int]]:
    return {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in directory.iterdir()}


def _make_existing_out(out: Path) -> dict[str, tuple[bytes, int]]:
    out.mkdir()
    for name in ("chr.bin", "assets.h", "nametable_0.s"):
        (out / name).write_bytes(b"old " + name.encode())
    return _snapshot(out)


def _no_temp_dirs(out: Path) -> bool:
    return not list(out.parent.glob(".chrono-*"))


# --- Success ---


def test_convert_success_writes_files_and_logs_assets(scene, capsys):
    manifest, out = scene
    assert convert(None, manifest, out) == 0
    captured = capsys.readouterr()
    assert (out / "chr.bin").stat().st_size == 8192
    assert (out / "assets.h").is_file()
    assert (out / "nametable_0.s").is_file()
    assert captured.err == ""
    for name in (
        "chr.bin",
        "assets.h",
        "nametable_0.s",
        "chr_bg",
        "chr_sprite",
        "nametable[0]",
        "attr[0]",
        "palette_bg",
        "palette_sprite",
        "metasprite_hero",
    ):
        pattern = re.escape(name) + r": \d+ bytes, crc32=[0-9a-f]{8}"
        assert re.search(pattern, captured.out), f"no length/CRC line for {name}"
    assert "chr.bin: 8192 bytes" in captured.out
    assert "nametable[0]: 960 bytes" in captured.out
    assert "attr[0]: 64 bytes" in captured.out


def test_run_pipeline_returns_result_and_emit(scene):
    manifest, out = scene
    result, emit = run_pipeline(None, manifest, out)
    assert len(result.chr_bin) == 8192
    assert set(emit.files) == {"chr.bin", "assets.h", "nametable_0.s"}
    assert all(path.is_file() for path in emit.files.values())


def test_run_pipeline_raises_conversion_error(scene):
    manifest, out = scene
    manifest.write_text(json.dumps(_manifest(screens=[{"tilemap": 0}])), encoding="utf-8")
    with pytest.raises(ConversionError):
        run_pipeline(None, manifest, out)
    assert not out.exists()


def test_pyxres_override_replaces_manifest_list(scene, tmp_path, capsys):
    manifest, out = scene
    other = tmp_path / "other.pyxres"
    (tmp_path / "game.pyxres").replace(other)  # the Manifest's own file is now missing
    assert convert([other], manifest, out) == 0
    assert (out / "chr.bin").is_file()


# --- Failures leave the output untouched ---


def _break_manifest(manifest: Path) -> None:
    manifest.write_text(json.dumps(_manifest(screens=[{"tilemap": "zero"}])), encoding="utf-8")


def _break_sprite_color(manifest: Path) -> None:
    # Sprite pixels use color 5, which this palette does not contain.
    manifest.write_text(
        json.dumps(_manifest(sprite_palettes={"sp0": [0, 6, 7, 8]})), encoding="utf-8"
    )


@pytest.mark.parametrize("breaker", [_break_manifest, _break_sprite_color])
def test_early_stage_failure_keeps_existing_output(scene, capsys, breaker):
    manifest, out = scene
    before = _make_existing_out(out)
    breaker(manifest)
    assert convert(None, manifest, out) == 1
    captured = capsys.readouterr()
    assert captured.err.startswith("error: ")
    assert captured.out == ""
    assert _snapshot(out) == before
    assert _no_temp_dirs(out)


def _failing_crc(exc: Exception):
    """Replace emitter's zlib so the failure happens after the first temp file is written."""

    def crc32(data):
        raise exc

    return SimpleNamespace(crc32=crc32)


@pytest.mark.parametrize(
    "exc",
    [ConversionError("emit boom"), OSError(28, "No space left on device")],
    ids=["ConversionError", "OSError"],
)
def test_emit_failure_keeps_existing_output(scene, capsys, monkeypatch, exc):
    manifest, out = scene
    before = _make_existing_out(out)
    monkeypatch.setattr(emitter, "zlib", _failing_crc(exc))
    assert convert(None, manifest, out) == 1
    captured = capsys.readouterr()
    assert captured.err.startswith("error: ")
    assert captured.out == ""
    assert _snapshot(out) == before
    assert _no_temp_dirs(out)


def test_emit_failure_without_existing_output_leaves_nothing(scene, monkeypatch, capsys):
    manifest, out = scene
    monkeypatch.setattr(emitter, "zlib", _failing_crc(OSError(5, "I/O error")))
    assert convert(None, manifest, out) == 1
    assert "error: " in capsys.readouterr().err
    assert not out.exists()
    assert _no_temp_dirs(out)


def test_success_after_failure_replaces_files_completely(scene, capsys):
    manifest, out = scene
    _make_existing_out(out)
    good = manifest.read_text(encoding="utf-8")
    _break_manifest(manifest)
    assert convert(None, manifest, out) == 1
    manifest.write_text(good, encoding="utf-8")
    capsys.readouterr()
    assert convert(None, manifest, out) == 0
    assert (out / "chr.bin").stat().st_size == 8192
    assert b"old " not in (out / "assets.h").read_bytes()
    assert b"old " not in (out / "nametable_0.s").read_bytes()
    assert sorted(p.name for p in out.iterdir()) == ["assets.h", "chr.bin", "nametable_0.s"]
    assert _no_temp_dirs(out)


# --- CLI ---


def test_main_parses_args_and_returns_exit_code(scene, capsys):
    manifest, out = scene
    assert main([str(manifest), "-o", str(out)]) == 0
    assert (out / "chr.bin").is_file()
    capsys.readouterr()
    assert main([str(manifest.with_name("missing.json")), "--out-dir", str(out)]) == 1
    assert "error: " in capsys.readouterr().err


def test_main_pyxres_option(scene, tmp_path):
    manifest, out = scene
    other = tmp_path / "other.pyxres"
    (tmp_path / "game.pyxres").replace(other)
    assert main([str(manifest), "-o", str(out), "--pyxres", str(other)]) == 0


def test_python_m_converter_without_args_exits_nonzero():
    proc = subprocess.run(
        [sys.executable, "-m", "converter"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode != 0
    assert "usage" in proc.stderr.lower()
