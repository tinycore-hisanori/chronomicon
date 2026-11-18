"""Palette_Quantizer: validate Manifest palettes and look up NES colors.

Pyxel colors map to NES 2C02 bytes only through the Manifest `nes_colors` table.
There is no RGB estimation and no automatic palette assignment.
"""

from __future__ import annotations

from .errors import ConversionError
from .models import ManifestData, PaletteDef, PaletteSet

MAX_PALETTES_PER_KIND = 4
MAX_COLORS_PER_PALETTE = 4


def pyxel_to_nes(palette_set: PaletteSet, pyxel_color: int) -> int:
    """nes_colors lookup. Raises ConversionError for an unknown index (Requirement 2.6)."""
    try:
        return palette_set.nes_colors[pyxel_color]
    except KeyError:
        raise ConversionError(
            f"Pyxel color index {pyxel_color} is not defined in the Manifest nes_colors table"
        ) from None


def _check_count(kind: str, palettes: tuple[PaletteDef, ...]) -> None:
    if len(palettes) > MAX_PALETTES_PER_KIND:
        raise ConversionError(
            f"Too many {kind} palettes: {len(palettes)} defined, "
            f"the limit is {MAX_PALETTES_PER_KIND}"
        )


def _check_palette(kind: str, palette: PaletteDef, nes_colors: dict[int, int]) -> None:
    for color in palette.pyxel_colors:
        if color not in nes_colors:
            raise ConversionError(
                f"Pyxel color index {color} used by {kind} palette '{palette.name}' "
                f"is not defined in the Manifest nes_colors table"
            )
    unique = len(set(palette.pyxel_colors))
    if unique > MAX_COLORS_PER_PALETTE:
        raise ConversionError(
            f"{kind} palette '{palette.name}' has {unique} unique colors, "
            f"the limit is {MAX_COLORS_PER_PALETTE}"
        )


def build_palettes(manifest: ManifestData) -> PaletteSet:
    """Validate palettes against nes_colors and return the PaletteSet."""
    nes_colors = manifest.nes_colors

    # Palette counts (2.2, 2.7)
    _check_count("BG", manifest.bg_palettes)
    _check_count("sprite", manifest.sprite_palettes)

    # nes_colors lookups and color counts (2.1, 2.3, 2.4, 2.6)
    for palette in manifest.bg_palettes:
        _check_palette("BG", palette, nes_colors)
    for palette in manifest.sprite_palettes:
        _check_palette("sprite", palette, nes_colors)

    # Common background color: color 0 of all BG palettes must be identical (2.9)
    bg = manifest.bg_palettes
    if bg:
        first = nes_colors[bg[0].pyxel_colors[0]]
        for palette in bg[1:]:
            value = nes_colors[palette.pyxel_colors[0]]
            if value != first:
                raise ConversionError(
                    f"BG palettes must share the same color 0: palette '{bg[0].name}' has "
                    f"color 0 = 0x{first:02X}, palette '{palette.name}' has color 0 = 0x{value:02X}"
                )

    return PaletteSet(bg=bg, sprite=manifest.sprite_palettes, nes_colors=dict(nes_colors))
