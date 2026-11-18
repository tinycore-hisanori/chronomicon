"""CHR_Encoder: 2 bpp tile encoding, BG pattern table construction.

Sprite encoding builds 8x16 pairs (upper tile at an even slot, lower at the next odd one)
on top of the same tile primitives.
"""

from __future__ import annotations

from .errors import ConversionError
from .models import (
    BGCHRResult,
    ImageBank,
    ManifestData,
    PaletteDef,
    PaletteSet,
    Resources,
    ScreenLayout,
    SpriteCHRResult,
    SpriteDef,
    SpritePair,
    SpritePairEntry,
    Tile8x8,
    TileRef,
)

PATTERN_TABLE_SIZE = 4096
BLANK_SLOT = 0x20  # font space glyph; blank BG tiles use it and consume no game slot
# Slots 0x20-0x7E are reserved for the font.
BG_GAME_SLOTS: tuple[int, ...] = tuple(range(0x00, 0x20)) + tuple(range(0x7F, 0x100))
BG_CAPACITY = len(BG_GAME_SLOTS)  # 161

# --- 2 bpp tile primitives (shared by BG and sprite encoding) ---


def encode_tile(indices: Tile8x8) -> bytes:
    """8x8 in-palette indices (0-3) -> 16 bytes, plane 0 then plane 1, bit 7 = leftmost."""
    plane0 = bytearray(8)
    plane1 = bytearray(8)
    for y in range(8):
        row = indices[y]
        b0 = 0
        b1 = 0
        for x in range(8):
            value = row[x]
            b0 |= (value & 1) << (7 - x)
            b1 |= ((value >> 1) & 1) << (7 - x)
        plane0[y] = b0
        plane1[y] = b1
    return bytes(plane0 + plane1)


def decode_tile(chr16: bytes) -> Tile8x8:
    """Inverse of `encode_tile`."""
    if len(chr16) != 16:
        raise ValueError(f"a CHR tile is 16 bytes, got {len(chr16)}")
    rows = []
    for y in range(8):
        b0 = chr16[y]
        b1 = chr16[y + 8]
        rows.append(
            tuple((((b1 >> (7 - x)) & 1) << 1) | ((b0 >> (7 - x)) & 1) for x in range(8))
        )
    return tuple(rows)


def cut_tile_pixels(
    bank: ImageBank, u: int, v: int, ref: TileRef, what: str = "tile"
) -> tuple[tuple[int, ...], ...]:
    """Cut the 8x8 Pyxel color pixels at (u, v) from an image bank."""
    if u < 0 or v < 0 or u + 8 > bank.width or v + 8 > bank.height:
        raise ConversionError(
            f"{what} (bank {ref.bank}, u={u}, v={v}) lies outside the image bank "
            f"({bank.width}x{bank.height})"
        )
    return tuple(tuple(bank.pixels[v + y][u : u + 8]) for y in range(8))


def to_palette_indices(
    pixels: tuple[tuple[int, ...], ...], palette: PaletteDef, ref: TileRef
) -> Tile8x8:
    """Map Pyxel colors to in-palette indices (first occurrence in the palette wins)."""
    lookup: dict[int, int] = {}
    for index, color in enumerate(palette.pyxel_colors):
        lookup.setdefault(color, index)
    rows = []
    for y in range(8):
        row = []
        for x in range(8):
            color = pixels[y][x]
            if color not in lookup:
                raise ConversionError(
                    f"tile (bank {ref.bank}, u={ref.u}, v={ref.v}) pixel (x={x}, y={y}) "
                    f"has Pyxel color {color}, which is not in assigned palette "
                    f"'{palette.name}'"
                )
            row.append(lookup[color])
        rows.append(tuple(row))
    return tuple(rows)


# --- BG encoding ---


def _collect_tiles(layouts: list[ScreenLayout], palette_set: PaletteSet) -> dict[TileRef, int]:
    """TileRef -> BG palette index (from the first cell that references the tile)."""
    found: dict[TileRef, int] = {}
    for layout in layouts:
        for row_tiles, row_pal in zip(layout.tiles, layout.palette_map):
            for ref, pal in zip(row_tiles, row_pal):
                if ref not in found:
                    if not 0 <= pal < len(palette_set.bg):
                        raise ConversionError(
                            f"screen {layout.screen_index}: tile (bank {ref.bank}, "
                            f"u={ref.u}, v={ref.v}) has BG palette number {pal}, "
                            f"but only {len(palette_set.bg)} BG palettes are defined"
                        )
                    found[ref] = pal
    return found


def encode_bg_tiles(
    layouts: list[ScreenLayout],
    resources: Resources,
    palette_set: PaletteSet,
    manifest: ManifestData,
) -> BGCHRResult:
    """Cut every referenced image tile, convert to in-palette indices, deduplicate and
    assign BG CHR slots. Raises ConversionError on a foreign pixel color or when more
    than 161 unique non-blank tiles are needed."""
    palette_of = _collect_tiles(layouts, palette_set)
    # Deterministic order: bank, then row-major (v, then u).
    ordered = sorted(palette_of, key=lambda r: (r.bank, r.v, r.u))

    unique: dict[Tile8x8, None] = {}  # insertion-ordered set of non-blank index arrays
    index_of: dict[TileRef, Tile8x8] = {}
    for ref in ordered:
        bank = resources.image_bank(ref.bank)
        if bank is None:
            raise ConversionError(f"tile (bank {ref.bank}, u={ref.u}, v={ref.v}): image bank does not exist")
        pixels = cut_tile_pixels(bank, ref.u, ref.v, ref)
        indices = to_palette_indices(pixels, palette_set.bg[palette_of[ref]], ref)
        index_of[ref] = indices
        if any(any(row) for row in indices):
            unique.setdefault(indices, None)

    if len(unique) > BG_CAPACITY:
        raise ConversionError(
            f"BG tiles: {len(unique)} unique non-blank tiles needed, "
            f"limit is {BG_CAPACITY}"
        )

    slot_of: dict[Tile8x8, int] = {}
    chr_bytes = bytearray(PATTERN_TABLE_SIZE)
    for indices, slot in zip(unique, BG_GAME_SLOTS):
        slot_of[indices] = slot
        chr_bytes[slot * 16 : slot * 16 + 16] = encode_tile(indices)

    tile_to_chr_id: dict[TileRef, int] = {}
    for ref in ordered:
        indices = index_of[ref]
        tile_to_chr_id[ref] = slot_of[indices] if indices in slot_of else BLANK_SLOT

    return BGCHRResult(
        chr_bytes=chr_bytes,
        tile_to_chr_id=tile_to_chr_id,
        num_game_tiles=len(unique),
    )


# --- Sprite encoding ---

SPRITE_PAIR_CAPACITY = PATTERN_TABLE_SIZE // 32  # 128 pairs = 256 tiles
SPRITE_TILE_CAPACITY = SPRITE_PAIR_CAPACITY * 2


def hflip_pair(pair: SpritePair) -> SpritePair:
    """Mirror both tiles of an 8x16 pair horizontally."""
    upper, lower = pair
    return (
        tuple(tuple(reversed(row)) for row in upper),
        tuple(tuple(reversed(row)) for row in lower),
    )


def oam_tile(pair_index: int) -> int:
    """OAM tile byte for a pair in 8x16 mode: bit 0 selects the pattern table (1 = $1000),
    bits 7-1 select the pair, so pair p (slots 2p, 2p+1) -> (2*p) | 1."""
    return (2 * pair_index) | 1


def _is_blank(tile: Tile8x8) -> bool:
    return not any(any(row) for row in tile)


def encode_sprite_tiles(
    sprite_defs: list[SpriteDef] | tuple[SpriteDef, ...],
    resources: Resources,
    palette_set: PaletteSet,
) -> SpriteCHRResult:
    """Cut each sprite into 8x16 cells, deduplicate pairs (also mirrored) and build the
    4096-byte sprite pattern table. Raises ConversionError on a foreign pixel color or
    when more than 128 unique pairs (256 tiles) are needed."""
    palettes = {p.name: p for p in palette_set.sprite}
    pairs: dict[SpritePair, int] = {}  # insertion-ordered: pair -> pair_index
    cell_map: dict[tuple[str, int, int], SpritePairEntry] = {}
    blank_cells: set[tuple[str, int, int]] = set()

    for sprite in sprite_defs:
        palette = palettes.get(sprite.palette)
        if palette is None:
            raise ConversionError(
                f"sprite '{sprite.name}': sprite palette '{sprite.palette}' is not defined"
            )
        bank = resources.image_bank(sprite.image_bank)
        if bank is None:
            raise ConversionError(
                f"sprite '{sprite.name}': image bank {sprite.image_bank} does not exist"
            )
        for cy in range(sprite.h // 16):
            for cx in range(sprite.w // 8):
                u = sprite.u + 8 * cx
                v = sprite.v + 16 * cy
                tiles = []
                for dv in (0, 8):
                    ref = TileRef(sprite.image_bank, u, v + dv)
                    pixels = cut_tile_pixels(
                        bank, u, v + dv, ref, what=f"sprite '{sprite.name}' tile"
                    )
                    tiles.append(to_palette_indices(pixels, palette, ref))
                pair: SpritePair = (tiles[0], tiles[1])
                key = (sprite.name, cx, cy)
                if _is_blank(pair[0]) and _is_blank(pair[1]):
                    blank_cells.add(key)
                    continue
                if pair in pairs:
                    cell_map[key] = SpritePairEntry(pairs[pair], False)
                    continue
                flipped = hflip_pair(pair)
                if flipped in pairs:
                    cell_map[key] = SpritePairEntry(pairs[flipped], True)
                    continue
                pairs[pair] = len(pairs)
                cell_map[key] = SpritePairEntry(pairs[pair], False)

    if len(pairs) > SPRITE_PAIR_CAPACITY:
        raise ConversionError(
            f"sprite tiles: {2 * len(pairs)} tiles needed, limit is {SPRITE_TILE_CAPACITY}"
        )

    chr_bytes = bytearray(PATTERN_TABLE_SIZE)
    for (upper, lower), index in pairs.items():
        chr_bytes[32 * index : 32 * index + 16] = encode_tile(upper)
        chr_bytes[32 * index + 16 : 32 * index + 32] = encode_tile(lower)

    return SpriteCHRResult(
        chr_bytes=chr_bytes, cell_map=cell_map, blank_cells=frozenset(blank_cells)
    )
