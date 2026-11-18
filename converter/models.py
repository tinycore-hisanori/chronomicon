"""Frozen dataclasses shared by all converter stages."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

Tile8x8 = tuple[tuple[int, ...], ...]  # 8 rows x 8 in-palette indices (0-3)
SpritePair = tuple[Tile8x8, Tile8x8]  # (upper, lower) 8x16 hardware sprite

# --- Pyxres loader ---


@dataclass(frozen=True)
class ImageBank:
    width: int
    height: int
    pixels: tuple[tuple[int, ...], ...]  # height rows x width Pyxel color indices (0-15)


@dataclass(frozen=True)
class Tilemap:
    width: int  # in tiles
    height: int
    imgsrc: int  # number of the image bank the cells point into
    # height rows x width (tx, ty), in 8 px units
    cells: tuple[tuple[tuple[int, int], ...], ...]


def cell_uv(cell: tuple[int, int]) -> tuple[int, int]:
    """Top-left pixel position (u, v) of the image tile a stored cell (tx, ty) points to."""
    tx, ty = cell
    return 8 * tx, 8 * ty


@dataclass(frozen=True)
class PyxresData:
    images: tuple[ImageBank, ...]  # index = bank number
    tilemaps: tuple[Tilemap, ...]  # index = tilemap number


@dataclass(frozen=True)
class Resources:
    """Loaded .pyxres files in Manifest listing order (= priority order)."""

    files: tuple[PyxresData, ...] = ()

    def image_bank(self, number: int) -> ImageBank | None:
        """Bank `number` from the first file that defines it, or None."""
        if number < 0:
            return None
        for data in self.files:
            if number < len(data.images):
                return data.images[number]
        return None

    def tilemap(self, number: int) -> Tilemap | None:
        """Tilemap `number` from the first file that defines it, or None."""
        if number < 0:
            return None
        for data in self.files:
            if number < len(data.tilemaps):
                return data.tilemaps[number]
        return None


# --- Manifest ---


@dataclass(frozen=True)
class PaletteDef:
    name: str
    pyxel_colors: tuple[int, ...]  # 1-4 Pyxel color indices; position = in-palette index


@dataclass(frozen=True)
class SpriteDef:
    name: str  # C identifier
    image_bank: int
    u: int
    v: int
    w: int  # multiple of 8
    h: int  # multiple of 16
    palette: str  # name of a sprite palette


@dataclass(frozen=True)
class BGPaletteRegion:
    image_bank: int
    u: int
    v: int
    w: int
    h: int
    palette: str  # name of a BG palette


@dataclass(frozen=True)
class ObjectDef:
    name: str  # name of a SpriteDef
    x: int  # display X in pixels, 0-255
    y: int  # display Y in pixels, 0-255 (the runtime writes y - 1 to OAM)
    screen: int = 0  # 0-based screen index inside the entry, 0..count-1


@dataclass(frozen=True)
class ScreenDef:
    tilemap: int
    x: int  # start tile column
    y: int  # start tile row
    count: int  # >= 1
    hud_tilemap: int
    hud_x: int
    hud_y: int
    objects: tuple[ObjectDef, ...] = ()  # optional initial placements


@dataclass(frozen=True)
class ManifestData:
    pyxres_files: tuple[str, ...]  # listing order = priority order
    nes_colors: dict[int, int]  # Pyxel color index -> NES 2C02 byte
    bg_palettes: tuple[PaletteDef, ...]  # at most 4
    sprite_palettes: tuple[PaletteDef, ...]  # at most 4
    bg_palette_regions: tuple[BGPaletteRegion, ...]
    sprites: tuple[SpriteDef, ...]
    screens: tuple[ScreenDef, ...]


@dataclass(frozen=True)
class PaletteSet:
    bg: tuple[PaletteDef, ...]
    sprite: tuple[PaletteDef, ...]
    nes_colors: dict[int, int]


# --- Screens ---


@dataclass(frozen=True)
class TileRef:
    bank: int
    u: int  # top-left pixel position of the image tile
    v: int


@dataclass(frozen=True)
class ScreenLayout:
    screen_index: int
    tiles: tuple[tuple[TileRef, ...], ...]  # 30 rows x 32 columns
    palette_map: tuple[tuple[int, ...], ...]  # 30 rows x 32 columns, values 0-3


# --- CHR ---


@dataclass(frozen=True)
class BGCHRResult:
    chr_bytes: bytearray  # 4096 bytes, font slots still empty
    tile_to_chr_id: dict[TileRef, int]
    num_game_tiles: int  # unique non-blank tiles, at most 161


@dataclass(frozen=True)
class SpritePairEntry:
    pair_index: int  # 0-127
    h_flip: bool  # True when stored mirrored


@dataclass(frozen=True)
class SpriteCHRResult:
    chr_bytes: bytearray  # 4096 bytes
    cell_map: dict[tuple[str, int, int], SpritePairEntry]  # (sprite name, cx, cy) -> entry
    blank_cells: frozenset[tuple[str, int, int]]  # cells skipped by 5.3


# --- Nametable / attribute ---


@dataclass(frozen=True)
class NametableData:
    screen_index: int
    tile_ids: tuple[int, ...]  # 960 values, 0-255


@dataclass(frozen=True)
class AttributeTable:
    screen_index: int
    data: bytes  # 64 bytes


# --- Metasprites ---


@dataclass(frozen=True)
class HWSprite:
    x_offset: int  # signed byte
    y_offset: int  # signed byte
    oam_tile: int  # upper_slot | 1
    attributes: int  # bits 1:0 palette, bit 6 horizontal flip


@dataclass(frozen=True)
class MetaspriteEntry:
    name: str
    width: int  # SpriteDef.w in pixels
    hw_sprites: tuple[HWSprite, ...]
    is_flip: bool


@dataclass(frozen=True)
class MetaspriteTable:
    entries: tuple[MetaspriteEntry, ...]  # normal then flipped, per sprite, Manifest order


# --- Output ---


@dataclass(frozen=True)
class ConversionResult:
    chr_bin: bytes  # 8192 bytes
    palette_set: PaletteSet
    nametables: tuple[NametableData, ...]
    attr_tables: tuple[AttributeTable, ...]
    metasprites: MetaspriteTable
    # Manifest screens (with objects) and SpriteDef names in Manifest order; used by the
    # Emitter to write the per-screen objects tables.
    screens: tuple[ScreenDef, ...] = ()
    sprite_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class EmitResult:
    files: dict[str, Path]
    checksums: dict[str, str]  # file name -> CRC-32 hex
    byte_lengths: dict[str, int]
