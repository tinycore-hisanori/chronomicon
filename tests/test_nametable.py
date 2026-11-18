"""Tests for converter.nametable."""
from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from converter.models import ScreenLayout, TileRef
from converter.nametable import build_nametables

_POOL = tuple(TileRef(bank=0, u=8 * i, v=0) for i in range(6))


@st.composite
def _layouts_and_map(draw):
    count = draw(st.integers(min_value=1, max_value=3))
    ids = draw(st.lists(st.integers(0, 255), min_size=len(_POOL), max_size=len(_POOL)))
    tile_to_chr_id = dict(zip(_POOL, ids))
    layouts = []
    for index in range(count):
        flat = draw(st.lists(st.sampled_from(_POOL), min_size=960, max_size=960))
        tiles = tuple(tuple(flat[r * 32 : (r + 1) * 32]) for r in range(30))
        palette_map = tuple((0,) * 32 for _ in range(30))
        layouts.append(ScreenLayout(screen_index=index, tiles=tiles, palette_map=palette_map))
    return layouts, tile_to_chr_id


# Feature: asset-converter, Property 5: Nametable tile ids stay in the CHR range
# **Validates: Requirements 3.2, 3.5**
@given(data=_layouts_and_map())
def test_nametable_ids_stay_in_chr_range(data):
    layouts, tile_to_chr_id = data
    tables = build_nametables(layouts, tile_to_chr_id)
    assert len(tables) == len(layouts)
    for layout, table in zip(layouts, tables):
        assert table.screen_index == layout.screen_index
        assert len(table.tile_ids) == 960
        assert all(0 <= i <= 255 for i in table.tile_ids)
        for row in range(30):
            for col in range(32):
                assert table.tile_ids[row * 32 + col] == tile_to_chr_id[layout.tiles[row][col]]


# --- Unit tests: HUD / BG sources and error messages (Requirements 3.1, 3.3, 3.5, 3.7) ---

import pytest  # noqa: E402

from converter.errors import ConversionError  # noqa: E402
from converter.models import (  # noqa: E402
    BGPaletteRegion,
    ManifestData,
    PaletteDef,
    PaletteSet,
    PyxresData,
    Resources,
    ScreenDef,
    Tilemap,
)
from converter.palette_map import build_screen_layouts  # noqa: E402

_BG_X, _BG_Y, _COUNT = 2, 1, 2
_HUD_X, _HUD_Y = 1, 2
_BG_BANK, _HUD_BANK = 0, 1


def _coord_tilemap(width, height, imgsrc):
    """Tilemap whose cell (c, r) holds the tile (tx, ty) = (c, r)."""
    cells = tuple(tuple((c, r) for c in range(width)) for r in range(height))
    return Tilemap(width=width, height=height, imgsrc=imgsrc, cells=cells)


def _chr_id(bank, tx, ty):
    return (bank * 100 + tx * 5 + ty * 11) % 256


def _scenario():
    bg_map = _coord_tilemap(_BG_X + 32 * _COUNT, _BG_Y + 30, _BG_BANK)
    hud_map = _coord_tilemap(_HUD_X + 32, _HUD_Y + 4, _HUD_BANK)
    palettes = (PaletteDef("p0", (0, 1, 2, 3)),)
    regions = tuple(BGPaletteRegion(b, 0, 0, 1024, 1024, "p0") for b in (_BG_BANK, _HUD_BANK))
    manifest = ManifestData(
        pyxres_files=("a.pyxres",),
        nes_colors={i: 0x0F for i in range(4)},
        bg_palettes=palettes,
        sprite_palettes=(),
        bg_palette_regions=regions,
        sprites=(),
        screens=(
            ScreenDef(
                tilemap=0, x=_BG_X, y=_BG_Y, count=_COUNT,
                hud_tilemap=1, hud_x=_HUD_X, hud_y=_HUD_Y,
            ),
        ),
    )
    resources = Resources(files=(PyxresData(images=(), tilemaps=(bg_map, hud_map)),))
    layouts = build_screen_layouts(
        manifest, resources, PaletteSet(bg=palettes, sprite=(), nes_colors=manifest.nes_colors)
    )
    tile_to_chr_id = {
        ref: _chr_id(ref.bank, ref.u // 8, ref.v // 8)
        for layout in layouts
        for row in layout.tiles
        for ref in row
    }
    return layouts, tile_to_chr_id


def test_hud_and_bg_rows_come_from_their_tilemaps():
    layouts, tile_to_chr_id = _scenario()
    tables = build_nametables(layouts, tile_to_chr_id)
    assert [t.screen_index for t in tables] == [0, 1]
    for i, table in enumerate(tables):
        assert len(table.tile_ids) == 960
        for offset in range(128):
            row, col = divmod(offset, 32)
            assert table.tile_ids[offset] == _chr_id(_HUD_BANK, _HUD_X + col, _HUD_Y + row)
        for offset in range(128, 960):
            row, col = divmod(offset, 32)
            expected = _chr_id(_BG_BANK, _BG_X + 32 * i + col, _BG_Y + row)
            assert table.tile_ids[offset] == expected


def test_missing_tile_error_names_column_row_screen_and_uv():
    layouts, tile_to_chr_id = _scenario()
    # Layout row 7, column 3 of screen 1 -> BG cell (c, r) = (2 + 32 + 3, 1 + 4 + 3).
    del tile_to_chr_id[TileRef(_BG_BANK, 8 * 37, 8 * 8)]
    with pytest.raises(ConversionError) as info:
        build_nametables(layouts, tile_to_chr_id)
    message = str(info.value)
    assert "screen 1" in message
    assert "column 3" in message
    assert "row 7" in message
    assert f"({8 * 37}, {8 * 8})" in message


@pytest.mark.parametrize("bad_id", [256, 1000, -1])
def test_out_of_range_chr_id_error_names_id_column_row_and_screen(bad_id):
    layouts, tile_to_chr_id = _scenario()
    # Layout row 2, column 5 of screen 0 -> HUD cell (1 + 5, 2 + 2).
    tile_to_chr_id[TileRef(_HUD_BANK, 8 * 6, 8 * 4)] = bad_id
    with pytest.raises(ConversionError) as info:
        build_nametables(layouts, tile_to_chr_id)
    message = str(info.value)
    assert "screen 0" in message
    assert f"CHR id {bad_id}" in message
    assert "column 5" in message
    assert "row 2" in message
