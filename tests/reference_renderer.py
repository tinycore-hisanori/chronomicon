"""Minimal reference PPU renderer used by the asset-converter tests.

Palette type accepted by :func:`render_nes_frame`
-------------------------------------------------
``bg_palettes`` and ``sprite_palettes`` are sequences of 4 palettes; each
palette is a sequence of 4 NES color bytes (ints 0-63), e.g.
``[[0x0F, 0x11, 0x21, 0x30], ...]`` or tuples. Fewer than 4 palettes are
allowed (missing ones are never referenced by valid input).

* BG: color 0 of every palette is ignored for output; the common background
  color is ``bg_palettes[0][0]``.
* Sprites: color index 0 is transparent; indices 1-3 map to
  ``sprite_palettes[attr & 3][index]``.

Output: a list of 240 rows, each a list of 256 NES color bytes.

Attribute table layout (standard): byte ``(ty // 4) * 8 + (tx // 4)``, each
byte holds four 2-bit palette numbers for 2x2-tile blocks: bits 1:0 top-left,
3:2 top-right, 5:4 bottom-left, 7:6 bottom-right.
"""

from __future__ import annotations

from typing import Sequence

from converter.models import MetaspriteEntry

SCREEN_W = 256
SCREEN_H = 240
NT_COLS = 32
NT_ROWS = 30

Palette = Sequence[int]
Oam = Sequence[tuple[int, int, int, int]]


def _tile_row_indices(chr_bin: bytes, table: int, tile: int, row: int) -> list[int]:
    """Return the 8 color indices (0-3) of one pixel row of a CHR tile."""
    base = table * 0x1000 + tile * 16 + row
    lo = chr_bin[base]
    hi = chr_bin[base + 8]
    return [(((hi >> (7 - x)) & 1) << 1) | ((lo >> (7 - x)) & 1) for x in range(8)]


def render_nes_frame(
    chr_bin: bytes,
    nametable: Sequence[int],
    attr: Sequence[int],
    bg_palettes: Sequence[Palette],
    sprite_palettes: Sequence[Palette],
    oam: Oam,
) -> list[list[int]]:
    """Render one 256x240 frame as rows of NES color bytes.

    ``chr_bin``: 8192 bytes (BG uses pattern table $0000; sprites pick by
    tile bit 0 in 8x16 mode). ``nametable``: 960 tile ids. ``attr``: 64 bytes.
    ``oam``: raw OAM tuples ``(y, tile, attr, x)``; sprite with OAM Y ``Y``
    covers screen rows ``Y + 1 .. Y + 16`` (rows >= 240 are clipped).
    Lower OAM index has priority; attr bit 5 puts a sprite behind opaque BG.
    """
    if len(nametable) != NT_COLS * NT_ROWS:
        raise ValueError(f"nametable must have 960 entries, got {len(nametable)}")
    if len(attr) != 64:
        raise ValueError(f"attribute table must have 64 bytes, got {len(attr)}")

    backdrop = bg_palettes[0][0]
    frame = [[backdrop] * SCREEN_W for _ in range(SCREEN_H)]
    bg_index = [[0] * SCREEN_W for _ in range(SCREEN_H)]

    # Background pass.
    for ty in range(NT_ROWS):
        for tx in range(NT_COLS):
            tile = nametable[ty * NT_COLS + tx]
            a = attr[(ty // 4) * 8 + (tx // 4)]
            shift = ((ty // 2) & 1) * 4 + ((tx // 2) & 1) * 2
            pal = bg_palettes[(a >> shift) & 3]
            for row in range(8):
                idxs = _tile_row_indices(chr_bin, 0, tile, row)
                y = ty * 8 + row
                for col, idx in enumerate(idxs):
                    x = tx * 8 + col
                    bg_index[y][x] = idx
                    if idx:
                        frame[y][x] = pal[idx]

    # Sprite pass: the lowest OAM index wins, so draw in reverse order.
    # An opaque pixel of a behind-background sprite still hides sprites of
    # lower priority, so track per-pixel sprite ownership.
    sprite_drawn = [[False] * SCREEN_W for _ in range(SCREEN_H)]
    for oam_y, tile, sattr, oam_x in oam:
        table = tile & 1
        top = tile & 0xFE
        hflip = bool(sattr & 0x40)
        vflip = bool(sattr & 0x80)
        behind = bool(sattr & 0x20)
        pal = sprite_palettes[sattr & 3]
        for r in range(16):
            y = oam_y + 1 + r
            if not 0 <= y < SCREEN_H:
                continue
            src = 15 - r if vflip else r
            t = top + (src >> 3)
            idxs = _tile_row_indices(chr_bin, table, t, src & 7)
            if hflip:
                idxs.reverse()
            for c, idx in enumerate(idxs):
                x = oam_x + c
                if idx == 0 or not 0 <= x < SCREEN_W or sprite_drawn[y][x]:
                    continue
                sprite_drawn[y][x] = True
                if behind and bg_index[y][x]:
                    continue
                frame[y][x] = pal[idx]
    return frame


def build_oam(
    metasprite: MetaspriteEntry, display_x: int, display_y: int
) -> list[tuple[int, int, int, int]]:
    """Build OAM tuples ``(y, tile, attr, x)`` for a metasprite placement.

    Each hardware sprite becomes
    ``(display_y - 1 + y_offset, oam_tile, attributes, display_x + x_offset)``.
    Raises ValueError when an OAM Y falls outside 0-239.
    """
    oam = []
    for hw in metasprite.hw_sprites:
        y = display_y - 1 + hw.y_offset
        if not 0 <= y <= 239:
            raise ValueError(f"OAM Y {y} outside 0-239")
        oam.append((y, hw.oam_tile, hw.attributes, display_x + hw.x_offset))
    return oam
