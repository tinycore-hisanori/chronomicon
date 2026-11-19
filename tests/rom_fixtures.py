"""Deterministic ROM test project: assets, manifests and mailbox ROM sources.

The project is written into a temporary directory; a ``.pyxres`` is never checked in.

Layout of the fixture assets:

* Image bank 0 (32x16 px): BG palette ``bg0`` owns tile row 0, ``bg1`` owns tile row 1.
  Tile (0, 0) is blank, tiles (1, 0), (2, 0), (0, 1), (1, 1) are distinct and non-blank.
* Image bank 1 (8x16 px): the sprite ``player``, every pixel opaque.
* Tilemap 0 holds two 32x30 screens side by side, tilemap 1 the 32x4 HUD source.
  Screen 0 uses palette ``bg0`` on the left half and ``bg1`` on the right half, screen 1 the
  opposite, with different tiles, so the two screens differ clearly. All palettes are
  assigned per aligned 2x2 tile block, so the attribute table can express them.

``samples/boot_test/manifest.json`` describes the same project with a relative
``pyxres_files: ["boot_test.pyxres"]``. JSON has no comments, so the note lives here:
the sample directory has no ``.pyxres``; :func:`write_sample_copy` copies the sample into a
temporary directory and writes ``boot_test.pyxres`` next to the manifest there.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from converter.models import ImageBank, Tilemap
from tests.pyxres_writer import write_pyxres

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DIR = REPO_ROOT / "samples" / "boot_test"
ROM_SRC_DIR = REPO_ROOT / "tests" / "rom"

SAMPLE_PYXRES_NAME = "boot_test.pyxres"
FIXTURE_PYXRES_NAME = "rom_fixture.pyxres"

_COLS = 32
_ROWS = 30
_HUD_ROWS = 4
_SCREENS = 2

# Pyxel color -> NES byte (injective; color 0 is the common backdrop).
_NES_COLORS = [
    0x0F, 0x11, 0x21, 0x31, 0x16, 0x26, 0x36, 0x1A,
    0x2A, 0x3A, 0x12, 0x22, 0x14, 0x24, 0x17, 0x27,
]
_BG_PALETTES = {"bg0": [0, 5, 6, 7], "bg1": [0, 8, 9, 10]}
_SPRITE_PALETTES = {"sp0": [0, 11, 12, 13]}


@dataclass(frozen=True)
class RomProject:
    """Paths of one written fixture project."""

    directory: Path
    pyxres: Path
    boot_manifest: Path
    password_manifest: Path
    runtime_manifest: Path


def _tile(colors: list[int], seed: int) -> list[list[int]]:
    """Non-blank 8x8 tile using every non-zero color of the palette (deterministic)."""
    pool = colors[1:]
    return [[pool[(x * 3 + y * 5 + seed) % len(pool)] for x in range(8)] for y in range(8)]


def _images() -> tuple[ImageBank, ImageBank]:
    bg = [[0] * 32 for _ in range(16)]
    tiles = {(1, 0): (0, 1), (2, 0): (0, 2), (0, 1): (1, 0), (1, 1): (1, 3)}
    for (tx, ty), (pal, seed) in tiles.items():
        colors = _BG_PALETTES[f"bg{pal}"]
        px = _tile(colors, seed)
        for y in range(8):
            bg[8 * ty + y][8 * tx : 8 * tx + 8] = px[y]
    sp_colors = _SPRITE_PALETTES["sp0"]
    sprite = [
        [sp_colors[1 + (x + y) % 3] for x in range(8)] for y in range(16)
    ]  # no color 0, so every pixel is opaque
    return (
        ImageBank(32, 16, tuple(tuple(r) for r in bg)),
        ImageBank(8, 16, tuple(tuple(r) for r in sprite)),
    )


def _screen_cells(screen: int) -> list[list[tuple[int, int]]]:
    """30 rows x 32 columns of (tx, ty) cells; rows 0-3 are overwritten by the HUD."""
    rows = []
    for r in range(_ROWS):
        row = []
        for c in range(_COLS):
            right = c >= _COLS // 2
            pal = (1 if right else 0) if screen == 0 else (0 if right else 1)
            if pal == 0:
                tx = 1 + ((r + c // 2 + screen) % 2)  # tiles (1,0) / (2,0)
            else:
                tx = (r // 2 + c // 2 + screen) % 2  # tiles (0,1) / (1,1)
            row.append((tx, pal))
        rows.append(row)
    return rows


def _hud_cells() -> list[list[tuple[int, int]]]:
    """32x4 cells, palette bg0 only (blank, (1,0), (2,0) in a repeating stripe)."""
    return [[((c // 2 + r // 2) % 3, 0) for c in range(_COLS)] for r in range(_HUD_ROWS)]


def _tilemaps() -> tuple[Tilemap, Tilemap]:
    hud = _hud_cells()
    cells = [[(0, 0)] * (_COLS * _SCREENS) for _ in range(_ROWS)]
    for s in range(_SCREENS):
        sc = _screen_cells(s)
        for r in range(_HUD_ROWS, _ROWS):
            cells[r][_COLS * s : _COLS * (s + 1)] = sc[r]
    for r in range(_HUD_ROWS):
        for s in range(_SCREENS):
            cells[r][_COLS * s : _COLS * (s + 1)] = hud[r]
    return (
        Tilemap(_COLS * _SCREENS, _ROWS, 0, tuple(tuple(r) for r in cells)),
        Tilemap(_COLS, _HUD_ROWS, 0, tuple(tuple(r) for r in hud)),
    )


def write_assets(pyxres_path: Path) -> None:
    """Write the fixture ``.pyxres`` to ``pyxres_path``."""
    images = _images()
    pyxres_path.parent.mkdir(parents=True, exist_ok=True)
    write_pyxres(pyxres_path, images, _tilemaps())


def converter_manifest(pyxres_name: str) -> dict[str, Any]:
    """Converter keys of the fixture project (relative ``pyxres_files``)."""
    return {
        "pyxres_files": [pyxres_name],
        "nes_colors": {str(i): v for i, v in enumerate(_NES_COLORS)},
        "bg_palettes": {k: list(v) for k, v in _BG_PALETTES.items()},
        "sprite_palettes": {k: list(v) for k, v in _SPRITE_PALETTES.items()},
        "bg_palette_regions": [
            {"image_bank": 0, "u": 0, "v": 0, "w": 32, "h": 8, "palette": "bg0"},
            {"image_bank": 0, "u": 0, "v": 8, "w": 32, "h": 8, "palette": "bg1"},
        ],
        "sprites": [
            {"name": "player", "image_bank": 1, "u": 0, "v": 0, "w": 8, "h": 16,
             "palette": "sp0"},
        ],
        "screens": [
            {"tilemap": 0, "x": 0, "y": 0, "count": _SCREENS,
             "hud_tilemap": 1, "hud_x": 0, "hud_y": 0},
        ],
    }


def build_manifest(
    name: str, game_sources: list[str], pyxres_name: str,
    prg_kb: int = 32, mirroring: str = "vertical",
) -> dict[str, Any]:
    """Full Builder manifest: Builder keys plus the converter keys."""
    manifest: dict[str, Any] = {
        "name": name,
        "game_sources": game_sources,
        "prg_kb": prg_kb,
        "mirroring": mirroring,
    }
    manifest.update(converter_manifest(pyxres_name))
    return manifest


def _write_json(path: Path, data: dict[str, Any]) -> Path:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def write_project(directory: Path) -> RomProject:
    """Write the fixture ``.pyxres`` and the three manifests into ``directory``."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    pyxres = directory / FIXTURE_PYXRES_NAME
    write_assets(pyxres)

    def manifest(name: str, source: Path) -> Path:
        data = build_manifest(name, [str(source.resolve())], FIXTURE_PYXRES_NAME)
        return _write_json(directory / f"{name}.json", data)

    return RomProject(
        directory=directory,
        pyxres=pyxres,
        boot_manifest=manifest("boot_test", SAMPLE_DIR / "main.c"),
        password_manifest=manifest("password_rom", ROM_SRC_DIR / "password_rom.c"),
        runtime_manifest=manifest("runtime_rom", ROM_SRC_DIR / "runtime_rom.c"),
    )


def write_sample_copy(directory: Path) -> Path:
    """Copy ``samples/boot_test`` into ``directory``, add ``boot_test.pyxres``; return the manifest."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SAMPLE_DIR / "main.c", directory / "main.c")
    shutil.copy2(SAMPLE_DIR / "manifest.json", directory / "manifest.json")
    write_assets(directory / SAMPLE_PYXRES_NAME)
    return directory / "manifest.json"
