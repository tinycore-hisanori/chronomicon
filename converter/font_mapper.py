"""Font_Mapper: write the bundled Pyxel 4x6 font into the BG pattern table.

Each ASCII code 0x20-0x7E gets the CHR slot equal to its code, so strings can be
copied straight into the nametable. Stroke pixels use palette index 3, everything
else index 0.
"""

from __future__ import annotations

from .chr_encoder import encode_tile
from .data.pyxel_font import FIRST_CODE, GLYPH_HEIGHT, GLYPH_WIDTH, GLYPHS, LAST_CODE

PATTERN_TABLE_SIZE = 4096
STROKE_INDEX = 3


def get_pyxel_glyph_pixels(code: int) -> tuple[tuple[int, ...], ...]:
    """8x8 index array (stroke 3, background 0) for an ASCII code in 0x20-0x7E."""
    if not isinstance(code, int) or not FIRST_CODE <= code <= LAST_CODE:
        raise ValueError(f"font code must be in 0x20-0x7E, got {code!r}")
    glyph = GLYPHS[code - FIRST_CODE]
    rows = []
    for y in range(8):
        if y < GLYPH_HEIGHT:
            mask = glyph[y]
            rows.append(
                tuple(
                    STROKE_INDEX if x < GLYPH_WIDTH and (mask >> (GLYPH_WIDTH - 1 - x)) & 1 else 0
                    for x in range(8)
                )
            )
        else:
            rows.append((0,) * 8)
    return tuple(rows)


def encode_font(chr_bytes: bytearray) -> bytearray:
    """Write the 95 font glyphs into slots 0x20-0x7E of a 4096-byte BG pattern table."""
    if len(chr_bytes) != PATTERN_TABLE_SIZE:
        raise ValueError(
            f"BG pattern table must be {PATTERN_TABLE_SIZE} bytes, got {len(chr_bytes)}"
        )
    for code in range(FIRST_CODE, LAST_CODE + 1):
        chr_bytes[code * 16 : code * 16 + 16] = encode_tile(get_pyxel_glyph_pixels(code))
    return chr_bytes
