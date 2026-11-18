"""Hypothesis strategies for valid Pyxel scenes (fidelity and determinism properties).

``valid_scenes()`` draws a :class:`Scene`: image banks, tilemaps, a Manifest dict in the
format read by ``converter.manifest.load_manifest``, the expected Pyxel-side composite of
every screen, and the sprite placements. ``write_scene`` writes the ``.pyxres`` and the
Manifest JSON to a directory.

Scene layout
------------
* Image bank 0 holds the BG tiles. BG palette ``i`` owns the 8 px high row band
  ``v = 8 * i`` (up to 4 tiles wide), declared as one ``bg_palette_regions`` rectangle.
  Tile ``(tx, ty)`` of the band belongs to palette ``ty``.
* Image bank 1 holds the sprites, stacked vertically (``u`` in {0, 8, 16}, bank width 32).
* Tilemap 0 is the BG source (``32 * count`` columns plus a start offset), tilemap 1 is the
  HUD source (32 columns by 4 rows plus an offset). Both point into image bank 0.
* Tiles are placed in aligned 2x2 blocks (screen coordinates) that share one palette, so the
  attribute table can express them. HUD rows 0-3 are two block rows, BG rows 4-29 are 13.
* ``nes_colors`` is injective and every BG palette starts with the same Pyxel color
  (the common background). Sprite palette color 0 is the transparent color.
* One Manifest screen entry with ``count`` of 1 or 2 screens. ``Placement.screen`` is the
  global screen index, which equals the ``screen`` field of a Manifest object.

Flipped placements
------------------
The Manifest object format cannot express a flip, so only non-flipped placements are
written to the Manifest ``objects`` list (the converter still validates and emits them).
A flipped placement means "draw ``metasprite_<name>_flip`` at (x, y)", and the Pyxel-side
composite uses the horizontally mirrored sprite image. The fidelity test builds its OAM
list from ``Scene.placements`` (all of them), so the flip entry is chosen by the test.

Placement order is OAM priority order: an earlier placement of a screen is drawn on top of
later ones, as the lower OAM index wins on hardware.

Placement bounds keep every OAM Y byte (``y - 1 + y_offset``) in 0-239 and every sprite
fully on-screen: ``1 <= y <= 240 - h`` and ``0 <= x <= 256 - w``.

Bulky pixel data comes from a ``random.Random`` seeded by one drawn integer, which keeps
the Hypothesis buffer small and generation fast (shrinking of pixel contents is coarse).
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hypothesis import strategies as st

from converter.models import ImageBank, Tilemap
from tests.pyxres_writer import write_pyxres

SCREEN_W = 256
SCREEN_H = 240
SCREEN_COLS = 32
SCREEN_ROWS = 30
HUD_ROWS = 4
MAX_SPRITES_PER_SCANLINE = 8
PYXRES_NAME = "scene.pyxres"
MANIFEST_NAME = "manifest.json"

_BG_BANK = 0
_SPRITE_BANK = 1
_BG_BAND_TILES = 4  # tiles per palette band
_SPRITE_BANK_W = 32

Frame = tuple[tuple[int, ...], ...]  # 240 rows x 256 Pyxel colors


@dataclass(frozen=True)
class Placement:
    screen: int  # global screen index (0-based)
    name: str  # sprite name
    x: int  # display X
    y: int  # display Y (the runtime writes y - 1 to OAM)
    flipped: bool  # True: draw metasprite_<name>_flip


@dataclass(frozen=True)
class Scene:
    images: tuple[ImageBank, ...] = field(repr=False)
    tilemaps: tuple[Tilemap, ...] = field(repr=False)
    manifest: dict[str, Any]  # JSON-serialisable; pyxres_files lists PYXRES_NAME
    nes_colors: dict[int, int]  # Pyxel color -> NES byte (injective)
    expected: tuple[Frame, ...] = field(repr=False)  # per screen, Pyxel colors
    placements: tuple[Placement, ...]  # every placement, in OAM priority order per screen
    sprite_images: dict[str, Frame] = field(repr=False)  # normal orientation, Pyxel colors

    @property
    def num_screens(self) -> int:
        return len(self.expected)

    def placements_on(self, screen: int) -> list[Placement]:
        return [p for p in self.placements if p.screen == screen]


# --- Scene building blocks ---


def _random_tile(rng: random.Random, colors: list[int]) -> list[list[int]]:
    """8x8 Pyxel color pixels from `colors`; about 1 in 7 tiles is blank (all colors[0])."""
    if rng.random() < 0.15:
        return [[colors[0]] * 8 for _ in range(8)]
    return [[colors[rng.randrange(len(colors))] for _ in range(8)] for _ in range(8)]


def _block_rows(rng: random.Random, block_rows: int, pools: list[int]) -> list[list[tuple[int, int]]]:
    """Tile cells (tx, ty) for `block_rows` rows of 2x2 blocks, one palette per block."""
    n_pal = len(pools)
    rows: list[list[tuple[int, int]]] = [[] for _ in range(2 * block_rows)]
    for br in range(block_rows):
        for bc in range(SCREEN_COLS // 2):
            pal = rng.randrange(n_pal)
            for dr in range(2):
                for _ in range(2):
                    rows[2 * br + dr].append((rng.randrange(pools[pal]), pal))
    return rows


def _scanline_ok(placed: list[tuple[int, int, int]], new: tuple[int, int, int]) -> bool:
    """placed/new are (y, w, h). True when no scanline exceeds 8 hardware sprites.

    Conservative: every 8 px column of a sprite counts, even when its cell is blank.
    """
    counts = [0] * SCREEN_H
    for y, w, h in [*placed, new]:
        for line in range(y, y + h):
            counts[line] += w // 8
    return max(counts) <= MAX_SPRITES_PER_SCANLINE


def _make_sprite(
    rng: random.Random, palette: list[int], w: int, h: int
) -> list[list[int]]:
    """Sprite pixels as Pyxel colors; palette[0] is the transparent color."""
    n = len(palette)
    idx = [
        [0 if rng.random() < 0.35 else rng.randrange(1, n) for _ in range(w)] for _ in range(h)
    ]
    if w == 16 and rng.random() < 0.3:  # right cell = mirrored left cell (pair dedup path)
        for row in idx:
            row[8:16] = row[0:8][::-1]
    if w * h > 8 * 16 and rng.random() < 0.3:  # blank one cell (skipped hardware sprite)
        cx, cy = rng.randrange(w // 8), rng.randrange(h // 16)
        for y in range(16 * cy, 16 * cy + 16):
            idx[y][8 * cx : 8 * cx + 8] = [0] * 8
    if not any(any(row) for row in idx):  # keep at least one opaque pixel
        idx[0][0] = 1
    return [[palette[i] for i in row] for row in idx]


def _flip_rows(img: Frame) -> Frame:
    return tuple(tuple(reversed(row)) for row in img)


# --- Strategy ---


@st.composite
def valid_scenes(draw: st.DrawFn) -> Scene:
    """A small valid scene (1-2 screens, a few tiles and sprites, up to 4 objects/screen)."""
    seed = draw(st.integers(0, 2**32 - 1))
    rng = random.Random(seed)

    count = draw(st.integers(1, 2))
    n_bg = draw(st.integers(1, 4))
    n_sp_pal = draw(st.integers(1, 4))
    n_sprites = draw(st.integers(1, 3))
    bg_x = draw(st.integers(0, 3))
    bg_y = draw(st.integers(0, 2))
    hud_x = draw(st.integers(0, 2))
    hud_y = draw(st.integers(0, 2))

    # Injective Pyxel -> NES color table.
    nes_values = rng.sample(range(64), 16)
    nes_colors = {i: nes_values[i] for i in range(16)}

    # Palettes: BG palettes share color 0; every palette has distinct colors.
    c0 = rng.randrange(16)
    others = [c for c in range(16) if c != c0]
    bg_palettes = [[c0] + rng.sample(others, rng.randint(1, 3)) for _ in range(n_bg)]
    sp_palettes = [rng.sample(range(16), rng.randint(2, 4)) for _ in range(n_sp_pal)]

    # Image bank 0: one band of BG tiles per palette.
    pools = [rng.randint(1, _BG_BAND_TILES) for _ in range(n_bg)]
    bg_pixels = [[c0] * (8 * _BG_BAND_TILES) for _ in range(8 * n_bg)]
    for pal, pal_colors in enumerate(bg_palettes):
        for j in range(pools[pal]):
            tile = _random_tile(rng, pal_colors)
            for y in range(8):
                bg_pixels[8 * pal + y][8 * j : 8 * j + 8] = tile[y]
    bg_bank = ImageBank(
        width=8 * _BG_BAND_TILES,
        height=8 * n_bg,
        pixels=tuple(tuple(r) for r in bg_pixels),
    )

    # Image bank 1: sprites stacked vertically.
    sprite_specs: list[dict[str, Any]] = []
    sprite_images: dict[str, Frame] = {}
    sp_pixels: list[list[int]] = []
    for i in range(n_sprites):
        w = rng.choice((8, 16))
        h = rng.choice((16, 32))
        u = rng.choice([0, 8, 16] if w == 16 else [0, 8, 16, 24])
        pal = rng.randrange(n_sp_pal)
        img = _make_sprite(rng, sp_palettes[pal], w, h)
        v = len(sp_pixels)
        for row in img:
            full = [0] * _SPRITE_BANK_W
            full[u : u + w] = row
            sp_pixels.append(full)
        name = f"spr{i}"
        sprite_specs.append(
            {"name": name, "image_bank": _SPRITE_BANK, "u": u, "v": v, "w": w, "h": h,
             "palette": f"sp{pal}"}
        )
        sprite_images[name] = tuple(tuple(r) for r in img)
    sp_bank = ImageBank(
        width=_SPRITE_BANK_W,
        height=len(sp_pixels),
        pixels=tuple(tuple(r) for r in sp_pixels),
    )

    # Tilemaps (cells are (tx, ty)); unused cells hold a valid filler tile.
    filler = (0, 0)
    hud_cells = _block_rows(rng, HUD_ROWS // 2, pools)
    screen_cells = [
        hud_cells + _block_rows(rng, (SCREEN_ROWS - HUD_ROWS) // 2, pools) for _ in range(count)
    ]
    bg_map = [[filler] * (bg_x + SCREEN_COLS * count) for _ in range(bg_y + SCREEN_ROWS)]
    for i in range(count):
        for r in range(HUD_ROWS, SCREEN_ROWS):
            bg_map[bg_y + r][bg_x + SCREEN_COLS * i : bg_x + SCREEN_COLS * (i + 1)] = (
                screen_cells[i][r]
            )
    hud_map = [[filler] * (hud_x + SCREEN_COLS) for _ in range(hud_y + HUD_ROWS)]
    for r in range(HUD_ROWS):
        hud_map[hud_y + r][hud_x : hud_x + SCREEN_COLS] = hud_cells[r]
    tilemaps = (
        Tilemap(
            width=bg_x + SCREEN_COLS * count,
            height=bg_y + SCREEN_ROWS,
            imgsrc=_BG_BANK,
            cells=tuple(tuple(r) for r in bg_map),
        ),
        Tilemap(
            width=hud_x + SCREEN_COLS,
            height=hud_y + HUD_ROWS,
            imgsrc=_BG_BANK,
            cells=tuple(tuple(r) for r in hud_map),
        ),
    )

    # Placements (draw order = OAM priority order, earlier on top).
    placements: list[Placement] = []
    for screen in range(count):
        placed: list[tuple[int, int, int]] = []
        for _ in range(draw(st.integers(0, 4))):
            spec = sprite_specs[draw(st.integers(0, n_sprites - 1))]
            w, h = spec["w"], spec["h"]
            x = draw(st.integers(0, SCREEN_W - w))
            y = draw(st.integers(1, SCREEN_H - h))
            flipped = draw(st.booleans())
            if not _scanline_ok(placed, (y, w, h)):
                continue
            placed.append((y, w, h))
            placements.append(Placement(screen, spec["name"], x, y, flipped))

    # Expected Pyxel-side composite per screen.
    expected = tuple(
        _composite(bg_bank, screen_cells[i], [p for p in placements if p.screen == i],
                   sprite_images, sp_palettes, sprite_specs)
        for i in range(count)
    )

    manifest: dict[str, Any] = {
        "pyxres_files": [PYXRES_NAME],
        "nes_colors": {str(k): v for k, v in nes_colors.items()},
        "bg_palettes": {f"bg{i}": list(p) for i, p in enumerate(bg_palettes)},
        "sprite_palettes": {f"sp{i}": list(p) for i, p in enumerate(sp_palettes)},
        "bg_palette_regions": [
            {"image_bank": _BG_BANK, "u": 0, "v": 8 * i, "w": 8 * _BG_BAND_TILES, "h": 8,
             "palette": f"bg{i}"}
            for i in range(n_bg)
        ],
        "sprites": sprite_specs,
        "screens": [_screen_entry(count, bg_x, bg_y, hud_x, hud_y, placements)],
    }
    return Scene(
        images=(bg_bank, sp_bank),
        tilemaps=tilemaps,
        manifest=manifest,
        nes_colors=nes_colors,
        expected=expected,
        placements=tuple(placements),
        sprite_images=sprite_images,
    )


def _screen_entry(
    count: int, bg_x: int, bg_y: int, hud_x: int, hud_y: int, placements: list[Placement]
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "tilemap": 0, "x": bg_x, "y": bg_y, "count": count,
        "hud_tilemap": 1, "hud_x": hud_x, "hud_y": hud_y,
    }
    objects = [
        {"name": p.name, "x": p.x, "y": p.y, "screen": p.screen}
        for p in placements
        if not p.flipped
    ]
    if objects:  # optional key
        entry["objects"] = objects
    return entry


def _composite(
    bg_bank: ImageBank,
    cells: list[list[tuple[int, int]]],
    placements: list[Placement],
    sprite_images: dict[str, Frame],
    sp_palettes: list[list[int]],
    sprite_specs: list[dict[str, Any]],
) -> Frame:
    """BG from the 30x32 cell grid, then sprites (last placement first, so earlier is on top)."""
    transparent = {
        s["name"]: sp_palettes[int(s["palette"][2:])][0] for s in sprite_specs
    }
    rows: list[list[int]] = []
    for tile_row in cells:
        for py in range(8):
            row: list[int] = []
            for tx, ty in tile_row:
                row.extend(bg_bank.pixels[8 * ty + py][8 * tx : 8 * tx + 8])
            rows.append(row)
    for p in reversed(placements):
        img = sprite_images[p.name]
        if p.flipped:
            img = _flip_rows(img)
        t = transparent[p.name]
        for dy, src in enumerate(img):
            dst = rows[p.y + dy]
            for dx, color in enumerate(src):
                if color != t:
                    dst[p.x + dx] = color
    return tuple(tuple(r) for r in rows)


# --- Writing ---


def write_scene(
    scene: Scene, directory: str | Path, compress: bool = False
) -> Path:
    """Write ``scene.pyxres`` and ``manifest.json`` to `directory`; return the Manifest path.

    The Manifest refers to the .pyxres by a relative path.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    write_pyxres(directory / PYXRES_NAME, scene.images, scene.tilemaps, compress=compress)
    manifest_path = directory / MANIFEST_NAME
    manifest_path.write_text(json.dumps(scene.manifest, indent=2), encoding="utf-8")
    return manifest_path
