"""Nametable construction: ScreenLayout tiles -> 960 CHR ids per screen."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from converter.errors import ConversionError
from converter.models import NametableData, ScreenLayout, TileRef

SCREEN_COLS = 32
SCREEN_ROWS = 30


def build_nametables(
    layouts: Sequence[ScreenLayout], tile_to_chr_id: Mapping[TileRef, int]
) -> list[NametableData]:
    """One NametableData per layout; id at offset ``row * 32 + col``.

    HUD rows 0-3 fill offsets 0-127 and BG rows 4-29 fill offsets 128-959.
    """
    result: list[NametableData] = []
    for layout in layouts:
        ids: list[int] = []
        for row in range(SCREEN_ROWS):
            for col in range(SCREEN_COLS):
                ref = layout.tiles[row][col]
                chr_id = tile_to_chr_id.get(ref)
                if chr_id is None:
                    raise ConversionError(
                        f"screen {layout.screen_index}: tile at column {col}, row {row} "
                        f"(Pyxel tile (u, v) = ({ref.u}, {ref.v}), image bank {ref.bank}) "
                        f"has no CHR id"
                    )
                if not 0 <= chr_id <= 255:
                    raise ConversionError(
                        f"screen {layout.screen_index}: CHR id {chr_id} at column {col}, "
                        f"row {row} is outside 0-255"
                    )
                ids.append(chr_id)
        result.append(NametableData(screen_index=layout.screen_index, tile_ids=tuple(ids)))
    return result
