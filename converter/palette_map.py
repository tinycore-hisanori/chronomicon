"""BG palette region lookup and per-screen tile/palette_map construction."""

from __future__ import annotations

from .errors import ConversionError
from .models import (
    BGPaletteRegion,
    ManifestData,
    PaletteSet,
    Resources,
    ScreenLayout,
    Tilemap,
    TileRef,
    cell_uv,
)

SCREEN_COLS = 32
SCREEN_ROWS = 30
HUD_ROWS = 4
BG_ROWS = SCREEN_ROWS - HUD_ROWS


def bg_palette_of_tile(
    regions: tuple[BGPaletteRegion, ...], bank: int, u: int, v: int
) -> str:
    """Name of the BG palette of the image tile whose top-left pixel is (u, v) in `bank`.

    Raises ConversionError when no region contains the tile (13.4) or when two regions
    with different palettes contain it (13.5). Overlapping regions naming the same
    palette are allowed.
    """
    found: str | None = None
    for region in regions:
        if region.image_bank != bank:
            continue
        if not (region.u <= u < region.u + region.w and region.v <= v < region.v + region.h):
            continue
        if found is None:
            found = region.palette
        elif found != region.palette:
            raise ConversionError(
                f"image tile (bank {bank}, u={u}, v={v}) is covered by bg_palette_regions "
                f"with different palettes: '{found}' and '{region.palette}'"
            )
    if found is None:
        raise ConversionError(
            f"image tile (bank {bank}, u={u}, v={v}) is not covered by any bg_palette_regions entry"
        )
    return found


def _check_region(
    tilemap: Tilemap,
    tilemap_number: int,
    screen_index: int,
    what: str,
    col: int,
    row: int,
    cols: int,
    rows: int,
) -> None:
    if col < 0 or row < 0 or col + cols > tilemap.width or row + rows > tilemap.height:
        raise ConversionError(
            f"screen {screen_index}: {what} region (column {col}, row {row}, "
            f"{cols}x{rows} tiles) is outside tilemap {tilemap_number} "
            f"(bounds {tilemap.width}x{tilemap.height} tiles)"
        )


def build_screen_layouts(
    manifest: ManifestData, resources: Resources, palette_set: PaletteSet
) -> list[ScreenLayout]:
    """Collect the 32x30 tile references and palette_map of every screen.

    Screens are numbered consecutively across entries in Manifest order and left to
    right inside an entry. Rows 0-3 come from the HUD source, rows 4-29 from the
    entry's tilemap.
    """
    palette_index = {p.name: i for i, p in enumerate(palette_set.bg)}
    palette_cache: dict[TileRef, int] = {}

    def palette_of(ref: TileRef) -> int:
        cached = palette_cache.get(ref)
        if cached is None:
            name = bg_palette_of_tile(manifest.bg_palette_regions, ref.bank, ref.u, ref.v)
            if name not in palette_index:
                raise ConversionError(
                    f"image tile (bank {ref.bank}, u={ref.u}, v={ref.v}) uses undefined "
                    f"BG palette '{name}'"
                )
            cached = palette_index[name]
            palette_cache[ref] = cached
        return cached

    def collect(
        tilemap: Tilemap, col: int, row: int, rows: int
    ) -> tuple[list[tuple[TileRef, ...]], list[tuple[int, ...]]]:
        tiles: list[tuple[TileRef, ...]] = []
        pals: list[tuple[int, ...]] = []
        for r in range(row, row + rows):
            refs = []
            for c in range(col, col + SCREEN_COLS):
                u, v = cell_uv(tilemap.cells[r][c])
                refs.append(TileRef(tilemap.imgsrc, u, v))
            tiles.append(tuple(refs))
            pals.append(tuple(palette_of(ref) for ref in refs))
        return tiles, pals

    layouts: list[ScreenLayout] = []
    screen_index = 0
    for entry in manifest.screens:
        bg_map = resources.tilemap(entry.tilemap)
        hud_map = resources.tilemap(entry.hud_tilemap)
        if bg_map is None:
            raise ConversionError(
                f"screen {screen_index}: tilemap {entry.tilemap} does not exist"
            )
        if hud_map is None:
            raise ConversionError(
                f"screen {screen_index}: HUD tilemap {entry.hud_tilemap} does not exist"
            )
        for i in range(entry.count):
            _check_region(
                hud_map, entry.hud_tilemap, screen_index, "HUD",
                entry.hud_x, entry.hud_y, SCREEN_COLS, HUD_ROWS,
            )
            _check_region(
                bg_map, entry.tilemap, screen_index, "screen",
                entry.x + SCREEN_COLS * i, entry.y + HUD_ROWS, SCREEN_COLS, BG_ROWS,
            )
            hud_tiles, hud_pals = collect(hud_map, entry.hud_x, entry.hud_y, HUD_ROWS)
            bg_tiles, bg_pals = collect(
                bg_map, entry.x + SCREEN_COLS * i, entry.y + HUD_ROWS, BG_ROWS
            )
            layouts.append(
                ScreenLayout(
                    screen_index=screen_index,
                    tiles=tuple(hud_tiles + bg_tiles),
                    palette_map=tuple(hud_pals + bg_pals),
                )
            )
            screen_index += 1
    return layouts
