"""Metasprite construction: SpriteDef -> 8x16 hardware sprite lists (normal and flipped)."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from converter.chr_encoder import oam_tile
from converter.models import (
    HWSprite,
    MetaspriteEntry,
    MetaspriteTable,
    PaletteSet,
    SpriteCHRResult,
    SpriteDef,
)

MAX_SPRITES_PER_ROW = 8
_FLIP_BIT = 0x40


def flip_metasprite(entry: MetaspriteEntry) -> MetaspriteEntry:
    """Mirror a metasprite horizontally. Applying it twice returns the original."""
    flipped = tuple(
        HWSprite(
            x_offset=entry.width - 8 - s.x_offset,
            y_offset=s.y_offset,
            oam_tile=s.oam_tile,
            attributes=s.attributes ^ _FLIP_BIT,
        )
        for s in entry.hw_sprites
    )
    return MetaspriteEntry(
        name=entry.name, width=entry.width, hw_sprites=flipped, is_flip=not entry.is_flip
    )


def build_metasprites(
    sprite_defs: Sequence[SpriteDef],
    sprite_chr: SpriteCHRResult,
    palette_set: PaletteSet,
) -> MetaspriteTable:
    """Build normal and flipped metasprites for each SpriteDef, in the given order."""
    palette_index = {p.name: i for i, p in enumerate(palette_set.sprite)}
    entries: list[MetaspriteEntry] = []
    for sd in sprite_defs:
        pal = palette_index[sd.palette]
        cols, rows = sd.w // 8, sd.h // 16
        hw: list[HWSprite] = []
        for cy in range(rows):
            row_count = 0
            for cx in range(cols):
                key = (sd.name, cx, cy)
                if key in sprite_chr.blank_cells:
                    continue
                pair = sprite_chr.cell_map[key]
                attr = (pal & 0x03) | (_FLIP_BIT if pair.h_flip else 0)
                hw.append(HWSprite(8 * cx, 16 * cy, oam_tile(pair.pair_index), attr))
                row_count += 1
            if row_count > MAX_SPRITES_PER_ROW:
                print(
                    f"warning: metasprite '{sd.name}' has {row_count} hardware sprites "
                    f"in one row (limit {MAX_SPRITES_PER_ROW} per scanline)",
                    file=sys.stderr,
                )
        normal = MetaspriteEntry(name=sd.name, width=sd.w, hw_sprites=tuple(hw), is_flip=False)
        entries.append(normal)
        entries.append(flip_metasprite(normal))
    return MetaspriteTable(entries=tuple(entries))
