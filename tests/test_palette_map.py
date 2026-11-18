"""Tests for converter.palette_map (BG palette lookup and screen layouts)."""

from __future__ import annotations

import random

from hypothesis import given
from hypothesis import strategies as st

from converter.models import (
    BGPaletteRegion,
    ImageBank,
    ManifestData,
    PaletteDef,
    PaletteSet,
    PyxresData,
    Resources,
    ScreenDef,
    Tilemap,
)
from converter.palette_map import build_screen_layouts

BANK_TILES = 8  # image bank is 8x8 tiles (64x64 px)
BANK_PX = BANK_TILES * 8


def _region_palette(regions, bank, u, v):
    """Independent rectangle test: palettes of all regions containing (u, v)."""
    return {
        r.palette
        for r in regions
        if r.image_bank == bank and r.u <= u < r.u + r.w and r.v <= v < r.v + r.h
    }


def _make_tilemap(rng, width, height, imgsrc):
    cells = tuple(
        tuple((rng.randrange(BANK_TILES), rng.randrange(BANK_TILES)) for _ in range(width))
        for _ in range(height)
    )
    return Tilemap(width=width, height=height, imgsrc=imgsrc, cells=cells)


@st.composite
def scenarios(draw):
    # Palette assigned to every image tile; names are shuffled into palette_set.bg order.
    tile_pal = [
        [draw(st.integers(0, 3)) for _ in range(BANK_TILES)] for _ in range(BANK_TILES)
    ]
    order = draw(st.permutations([0, 1, 2, 3]))  # bg slot k holds palette named p{order[k]}
    bg = tuple(PaletteDef(f"p{order[k]}", (0, 1, 2, 3)) for k in range(4))

    # Regions: per row, maximal runs of one palette become one region (non-overlapping).
    # Optionally add a full-bank-row duplicate region of the same palette (same-palette overlap).
    regions = []
    for ty in range(BANK_TILES):
        tx = 0
        while tx < BANK_TILES:
            end = tx
            while end + 1 < BANK_TILES and tile_pal[ty][end + 1] == tile_pal[ty][tx]:
                end += 1
            regions.append(
                BGPaletteRegion(0, tx * 8, ty * 8, (end - tx + 1) * 8, 8, f"p{tile_pal[ty][tx]}")
            )
            tx = end + 1
    if draw(st.booleans()):
        ty = draw(st.integers(0, BANK_TILES - 1))
        tx = draw(st.integers(0, BANK_TILES - 1))
        regions.append(BGPaletteRegion(0, tx * 8, ty * 8, 8, 8, f"p{tile_pal[ty][tx]}"))
    regions = draw(st.permutations(regions))

    seed = draw(st.integers(0, 2**32 - 1))
    rng = random.Random(seed)
    count = draw(st.integers(1, 2))
    bg_width = 32 * count + draw(st.integers(0, 32 if count == 1 else 0))
    bg_x = draw(st.integers(0, bg_width - 32 * count))
    bg_y = draw(st.integers(0, 2))
    bg_height = 30 + bg_y + draw(st.integers(0, 2))
    hud_width = draw(st.sampled_from([32, 40]))
    hud_x = draw(st.integers(0, hud_width - 32))
    hud_y = draw(st.integers(0, 2))
    hud_height = 4 + hud_y + draw(st.integers(0, 1))

    bg_map = _make_tilemap(rng, bg_width, bg_height, 0)
    hud_map = _make_tilemap(rng, hud_width, hud_height, 0)
    resources = Resources(
        files=(
            PyxresData(
                images=(ImageBank(BANK_PX, BANK_PX, tuple((0,) * BANK_PX for _ in range(BANK_PX))),),
                tilemaps=(bg_map, hud_map),
            ),
        )
    )
    entry = ScreenDef(
        tilemap=0, x=bg_x, y=bg_y, count=count, hud_tilemap=1, hud_x=hud_x, hud_y=hud_y
    )
    manifest = ManifestData(
        pyxres_files=("a.pyxres",),
        nes_colors={i: 0x0F for i in range(4)},
        bg_palettes=bg,
        sprite_palettes=(),
        bg_palette_regions=tuple(regions),
        sprites=(),
        screens=(entry,),
    )
    palette_set = PaletteSet(bg=bg, sprite=(), nes_colors=manifest.nes_colors)
    return manifest, resources, palette_set


# Feature: asset-converter, Property 13: palette_map consistency
# **Validates: Requirements 13.2, 13.3, 13.8**
@given(scenarios())
def test_palette_map_matches_region_palette(scenario):
    manifest, resources, palette_set = scenario
    layouts = build_screen_layouts(manifest, resources, palette_set)
    entry = manifest.screens[0]
    bg_map = resources.tilemap(entry.tilemap)
    hud_map = resources.tilemap(entry.hud_tilemap)
    slot_of = {p.name: i for i, p in enumerate(palette_set.bg)}

    assert len(layouts) == entry.count
    for i, layout in enumerate(layouts):
        assert layout.screen_index == i
        assert len(layout.tiles) == 30 and len(layout.palette_map) == 30
        for r in range(30):
            assert len(layout.tiles[r]) == 32 and len(layout.palette_map[r]) == 32
            for c in range(32):
                if r < 4:
                    tx, ty = hud_map.cells[entry.hud_y + r][entry.hud_x + c]
                else:
                    tx, ty = bg_map.cells[entry.y + r][entry.x + 32 * i + c]
                ref = layout.tiles[r][c]
                assert (ref.bank, ref.u, ref.v) == (0, 8 * tx, 8 * ty)
                names = _region_palette(manifest.bg_palette_regions, 0, ref.u, ref.v)
                assert len(names) == 1
                value = layout.palette_map[r][c]
                assert 0 <= value <= 3
                assert value == slot_of[next(iter(names))]


# ---------------------------------------------------------------------------
# Unit tests (Requirements 3.4, 13.4, 13.5, 14.5)
# ---------------------------------------------------------------------------

import pytest  # noqa: E402

from converter.errors import ConversionError  # noqa: E402
from converter.palette_map import bg_palette_of_tile  # noqa: E402


def test_bg_palette_of_tile_no_region_reports_bank_u_v():
    regions = (BGPaletteRegion(0, 0, 0, 8, 8, "p0"),)
    with pytest.raises(ConversionError) as exc:
        bg_palette_of_tile(regions, 0, 16, 24)
    msg = str(exc.value)
    assert "bank 0" in msg and "u=16" in msg and "v=24" in msg


def test_bg_palette_of_tile_conflicting_regions_report_both_palettes():
    regions = (
        BGPaletteRegion(1, 0, 0, 16, 16, "alpha"),
        BGPaletteRegion(1, 8, 8, 16, 16, "beta"),
    )
    with pytest.raises(ConversionError) as exc:
        bg_palette_of_tile(regions, 1, 8, 8)
    msg = str(exc.value)
    assert "bank 1" in msg and "u=8" in msg and "v=8" in msg
    assert "alpha" in msg and "beta" in msg


def test_bg_palette_of_tile_same_palette_overlap_is_accepted():
    regions = (
        BGPaletteRegion(0, 0, 0, 16, 16, "p1"),
        BGPaletteRegion(0, 8, 8, 16, 16, "p1"),
    )
    assert bg_palette_of_tile(regions, 0, 8, 8) == "p1"


def test_bg_palette_of_tile_ignores_regions_of_other_banks():
    regions = (
        BGPaletteRegion(1, 0, 0, 64, 64, "other"),
        BGPaletteRegion(0, 0, 0, 64, 64, "mine"),
    )
    assert bg_palette_of_tile(regions, 0, 8, 8) == "mine"
    # A region in another bank alone does not cover the tile.
    with pytest.raises(ConversionError):
        bg_palette_of_tile(regions[:1], 0, 8, 8)


def _layout_fixture(tilemaps, screens):
    bg = (
        PaletteDef("p0", (0, 1, 2, 3)),
        PaletteDef("p1", (0, 1, 2, 3)),
        PaletteDef("p2", (0, 1, 2, 3)),
        PaletteDef("p3", (0, 1, 2, 3)),
    )
    manifest = ManifestData(
        pyxres_files=("a.pyxres",),
        nes_colors={i: 0x0F for i in range(4)},
        bg_palettes=bg,
        sprite_palettes=(),
        bg_palette_regions=(BGPaletteRegion(0, 0, 0, BANK_PX, BANK_PX, "p0"),),
        sprites=(),
        screens=tuple(screens),
    )
    resources = Resources(
        files=(
            PyxresData(
                images=(ImageBank(BANK_PX, BANK_PX, tuple((0,) * BANK_PX for _ in range(BANK_PX))),),
                tilemaps=tuple(tilemaps),
            ),
        )
    )
    return manifest, resources, PaletteSet(bg=bg, sprite=(), nes_colors=manifest.nes_colors)


def _coord_map(width, height):
    """Tilemap whose cell at (col, row) is ((col // 8) % 8, row % 8)."""
    cells = tuple(
        tuple(((c // 8) % BANK_TILES, r % BANK_TILES) for c in range(width))
        for r in range(height)
    )
    return Tilemap(width=width, height=height, imgsrc=0, cells=cells)


def test_build_screen_layouts_numbers_screens_across_entries():
    # tilemap 0 is 64 wide (two screens), tilemap 1 is the HUD source.
    manifest, resources, pset = _layout_fixture(
        [_coord_map(64, 30), _coord_map(32, 4)],
        [
            ScreenDef(tilemap=0, x=0, y=0, count=2, hud_tilemap=1, hud_x=0, hud_y=0),
            ScreenDef(tilemap=0, x=0, y=0, count=1, hud_tilemap=1, hud_x=0, hud_y=0),
        ],
    )
    layouts = build_screen_layouts(manifest, resources, pset)
    assert [l.screen_index for l in layouts] == [0, 1, 2]


def test_build_screen_layouts_hud_and_bg_sources():
    # HUD at (1, 1) in a 33x5 map; BG at x=2, y=1, two screens in a 66x31 map.
    manifest, resources, pset = _layout_fixture(
        [_coord_map(66, 31), _coord_map(33, 5)],
        [ScreenDef(tilemap=0, x=2, y=1, count=2, hud_tilemap=1, hud_x=1, hud_y=1)],
    )
    layouts = build_screen_layouts(manifest, resources, pset)
    assert len(layouts) == 2
    for i, layout in enumerate(layouts):
        # HUD rows 0-3 come from the HUD map at (hud_x + c, hud_y + r).
        for r in range(4):
            for c in (0, 31):
                ref = layout.tiles[r][c]
                col, row = 1 + c, 1 + r
                assert (ref.u, ref.v) == (8 * ((col // 8) % 8), 8 * (row % 8))
        # BG rows 4-29 come from (x + 32*i + c, y + r).
        for r in (4, 29):
            for c in (0, 31):
                ref = layout.tiles[r][c]
                col, row = 2 + 32 * i + c, 1 + r
                assert (ref.u, ref.v) == (8 * ((col // 8) % 8), 8 * (row % 8))


def test_build_screen_layouts_bg_out_of_bounds():
    # Second screen needs columns 32..63 but the map is only 63 wide.
    manifest, resources, pset = _layout_fixture(
        [_coord_map(63, 30), _coord_map(32, 4)],
        [ScreenDef(tilemap=0, x=0, y=0, count=2, hud_tilemap=1, hud_x=0, hud_y=0)],
    )
    with pytest.raises(ConversionError) as exc:
        build_screen_layouts(manifest, resources, pset)
    msg = str(exc.value)
    assert "screen 1" in msg and "tilemap 0" in msg and "63x30" in msg


def test_build_screen_layouts_hud_out_of_bounds():
    # HUD map has only 3 rows, the HUD needs 4.
    manifest, resources, pset = _layout_fixture(
        [_coord_map(32, 30), _coord_map(32, 3)],
        [ScreenDef(tilemap=0, x=0, y=0, count=1, hud_tilemap=1, hud_x=0, hud_y=0)],
    )
    with pytest.raises(ConversionError) as exc:
        build_screen_layouts(manifest, resources, pset)
    msg = str(exc.value)
    assert "screen 0" in msg and "tilemap 1" in msg and "32x3" in msg
