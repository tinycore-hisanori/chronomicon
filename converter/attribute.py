"""Attribute_Builder: 32x30 per-cell palette map -> 64-byte attribute table.

Each attribute byte covers a 32x32 pixel area made of four 16x16 blocks:
bits 1:0 top-left, 3:2 top-right, 5:4 bottom-left, 7:6 bottom-right.
The last block row (block row 14) has no bottom half, so its bottom bits are 0.
"""

from __future__ import annotations

from .errors import ConversionError
from .models import AttributeTable

COLS = 32
ROWS = 30
BLOCK_COLS = 16
BLOCK_ROWS = 15
TABLE_SIZE = 64


def build_attribute_table(screen_index: int, palette_map: list[list[int]]) -> AttributeTable:
    """Build the attribute table of one screen from a 32x30 palette map.

    Raises ConversionError on a palette number outside 0-3 or a 16x16 block
    whose 8x8 cells use different palette numbers.
    """
    if len(palette_map) != ROWS or any(len(row) != COLS for row in palette_map):
        raise ConversionError(
            f"screen {screen_index}: palette map must be {COLS}x{ROWS} cells"
        )

    for y in range(ROWS):
        for x in range(COLS):
            value = palette_map[y][x]
            if not 0 <= value <= 3:
                raise ConversionError(
                    f"screen {screen_index}: palette number {value} at cell "
                    f"(column {x}, row {y}) is outside 0-3"
                )

    block_palette: list[list[int]] = []
    for by in range(BLOCK_ROWS):
        row_out: list[int] = []
        for bx in range(BLOCK_COLS):
            cells = [
                palette_map[2 * by + dy][2 * bx + dx] for dy in (0, 1) for dx in (0, 1)
            ]
            used = sorted(set(cells))
            if len(used) > 1:
                raise ConversionError(
                    f"screen {screen_index}: 16x16 block (column {bx}, row {by}) "
                    f"mixes palettes {used}"
                )
            row_out.append(cells[0])
        block_palette.append(row_out)

    data = bytearray(TABLE_SIZE)
    for ay in range(8):
        for ax in range(8):
            tl = block_palette[2 * ay][2 * ax]
            tr = block_palette[2 * ay][2 * ax + 1]
            has_bottom = 2 * ay + 1 < BLOCK_ROWS
            bl = block_palette[2 * ay + 1][2 * ax] if has_bottom else 0
            br = block_palette[2 * ay + 1][2 * ax + 1] if has_bottom else 0
            data[ay * 8 + ax] = tl | (tr << 2) | (bl << 4) | (br << 6)

    return AttributeTable(screen_index=screen_index, data=bytes(data))
