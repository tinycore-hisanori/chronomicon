"""Unit tests for the reference PPU renderer (tests/reference_renderer.py)."""

from __future__ import annotations

import pytest

from converter.models import HWSprite, MetaspriteEntry
from tests.reference_renderer import build_oam, render_nes_frame

BACKDROP = 0x0F
BG_PALS = [
    [BACKDROP, 0x01, 0x02, 0x03],
    [BACKDROP, 0x11, 0x12, 0x13],
    [BACKDROP, 0x21, 0x22, 0x23],
    [BACKDROP, 0x31, 0x32, 0x33],
]
SPR_PALS = [
    [BACKDROP, 0x04, 0x05, 0x06],
    [BACKDROP, 0x14, 0x15, 0x16],
    [BACKDROP, 0x24, 0x25, 0x26],
    [BACKDROP, 0x34, 0x35, 0x36],
]
EMPTY_NT = [255] * 960  # tile 255 is blank in every test CHR
EMPTY_ATTR = [0] * 64


def put_tile(chr_bin: bytearray, table: int, tile: int, rows: list[list[int]]) -> None:
    """Write an 8x8 tile given as 8 rows of 8 color indices (0-3) as 2bpp planes."""
    base = table * 0x1000 + tile * 16
    for r, idxs in enumerate(rows):
        lo = hi = 0
        for x, idx in enumerate(idxs):
            lo |= (idx & 1) << (7 - x)
            hi |= ((idx >> 1) & 1) << (7 - x)
        chr_bin[base + r] = lo
        chr_bin[base + 8 + r] = hi


def solid(idx: int) -> list[list[int]]:
    return [[idx] * 8 for _ in range(8)]


def new_chr() -> bytearray:
    return bytearray(8192)


def render(chr_bin, oam=(), nt=EMPTY_NT, attr=EMPTY_ATTR):
    return render_nes_frame(bytes(chr_bin), nt, attr, BG_PALS, SPR_PALS, list(oam))


def sprite_chr(idx: int = 1) -> bytearray:
    """CHR with a solid 8x16 sprite (tiles 0 and 1 of table 0 -> tile id 0)."""
    c = new_chr()
    put_tile(c, 0, 0, solid(idx))
    put_tile(c, 0, 1, solid(idx))
    return c


# --- sprite vertical placement -------------------------------------------


def test_sprite_oam_y_10_covers_rows_11_to_26():
    frame = render(sprite_chr(), [(10, 0, 0, 0)])
    rows = [y for y in range(240) if frame[y][0] == SPR_PALS[0][1]]
    assert rows == list(range(11, 27))
    assert frame[10][0] == BACKDROP and frame[27][0] == BACKDROP


def test_sprite_clipped_below_row_239():
    frame = render(sprite_chr(), [(235, 0, 0, 8)])
    rows = [y for y in range(240) if frame[y][8] == SPR_PALS[0][1]]
    assert rows == list(range(236, 240))
    assert len(frame) == 240


def test_sprite_oam_y_239_visible_nowhere_but_does_not_crash():
    frame = render(sprite_chr(), [(239, 0, 0, 0)])
    assert all(p == BACKDROP for row in frame for p in row)


def test_sprite_clipped_at_right_edge():
    frame = render(sprite_chr(), [(0, 0, 0, 252)])
    assert [x for x in range(256) if frame[1][x] != BACKDROP] == [252, 253, 254, 255]


# --- build_oam -------------------------------------------------------------


def _meta(*hw: HWSprite) -> MetaspriteEntry:
    return MetaspriteEntry(name="s", width=16, hw_sprites=tuple(hw), is_flip=False)


def test_build_oam_formula():
    m = _meta(HWSprite(0, 0, 1, 0), HWSprite(8, 16, 3, 0x41))
    assert build_oam(m, 100, 50) == [(49, 1, 0, 100), (65, 3, 0x41, 108)]


def test_build_oam_negative_x_offset():
    m = _meta(HWSprite(-8, 0, 1, 0))
    assert build_oam(m, 20, 10) == [(9, 1, 0, 12)]


@pytest.mark.parametrize("display_y, y_offset", [(0, 0), (241, 0), (10, -10), (250, 0)])
def test_build_oam_rejects_y_outside_0_239(display_y, y_offset):
    with pytest.raises(ValueError):
        build_oam(_meta(HWSprite(0, y_offset, 1, 0)), 0, display_y)


@pytest.mark.parametrize("display_y, y_offset", [(1, 0), (200, 39), (240, 0)])
def test_build_oam_accepts_boundary_y(display_y, y_offset):
    oam = build_oam(_meta(HWSprite(0, y_offset, 1, 0)), 0, display_y)
    assert 0 <= oam[0][0] <= 239


def test_build_oam_then_render_places_first_row_at_display_y():
    m = _meta(HWSprite(0, 0, 1, 0))
    c = new_chr()
    put_tile(c, 1, 0, solid(1))  # oam_tile 1 selects pattern table 1, pair (0, 1)
    put_tile(c, 1, 1, solid(1))
    frame = render(c, build_oam(m, 5, 30))
    assert frame[30][5] == SPR_PALS[0][1]
    assert frame[29][5] == BACKDROP


# --- background -------------------------------------------------------------


def test_bg_tile_uses_attribute_selected_palette():
    c = new_chr()
    put_tile(c, 0, 1, solid(2))
    nt = [0] * 960
    attr = [0] * 64
    # Tile (tx=2, ty=2) is in attribute byte 0, block bottom-right -> bits 7:6.
    nt[2 * 32 + 2] = 1
    attr[0] = 0b10_00_00_00
    frame = render(c, nt=nt, attr=attr)
    assert frame[16][16] == BG_PALS[2][2]
    assert frame[23][23] == BG_PALS[2][2]
    assert frame[16][24] == BACKDROP


def test_bg_attribute_quadrants():
    c = new_chr()
    put_tile(c, 0, 1, solid(1))
    nt = [1] * 960
    attr = [0] * 64
    attr[0] = 0b11_10_01_00  # TL=0, TR=1, BL=2, BR=3
    frame = render(c, nt=nt, attr=attr)
    assert frame[0][0] == BG_PALS[0][1]
    assert frame[0][16] == BG_PALS[1][1]
    assert frame[16][0] == BG_PALS[2][1]
    assert frame[16][16] == BG_PALS[3][1]


def test_bg_index_zero_shows_backdrop():
    frame = render(new_chr())
    assert all(p == BACKDROP for row in frame for p in row)


def test_bad_nametable_or_attr_length_raises():
    with pytest.raises(ValueError):
        render_nes_frame(bytes(8192), [0] * 10, EMPTY_ATTR, BG_PALS, SPR_PALS, [])
    with pytest.raises(ValueError):
        render_nes_frame(bytes(8192), EMPTY_NT, [0] * 3, BG_PALS, SPR_PALS, [])


# --- sprite details ---------------------------------------------------------


def test_sprite_horizontal_flip():
    c = new_chr()
    rows = [[1, 0, 0, 0, 0, 0, 0, 2]] * 8
    put_tile(c, 0, 0, rows)
    put_tile(c, 0, 1, rows)
    plain = render(c, [(0, 0, 0x00, 0)])
    flipped = render(c, [(0, 0, 0x40, 0)])
    assert plain[1][0] == SPR_PALS[0][1] and plain[1][7] == SPR_PALS[0][2]
    assert flipped[1][0] == SPR_PALS[0][2] and flipped[1][7] == SPR_PALS[0][1]


def test_sprite_palette_from_attr_low_bits():
    frame = render(sprite_chr(), [(0, 0, 0x02, 0)])
    assert frame[1][0] == SPR_PALS[2][1]


def test_sprite_index_zero_is_transparent_over_bg():
    c = new_chr()
    put_tile(c, 0, 1, solid(1))  # BG tile
    put_tile(c, 0, 2, [[0, 3] * 4] * 8)  # sprite top: transparent at even x
    put_tile(c, 0, 3, [[0, 3] * 4] * 8)
    nt = [1] * 960
    frame = render(c, [(0, 2, 0, 0)], nt=nt)
    assert frame[1][0] == BG_PALS[0][1]  # BG shows through
    assert frame[1][1] == SPR_PALS[0][3]


def test_sprite_behind_background_hidden_by_opaque_bg_only():
    c = new_chr()
    put_tile(c, 0, 1, solid(1))  # opaque BG tile at nametable (0,0)
    put_tile(c, 0, 2, solid(2))
    put_tile(c, 0, 3, solid(2))
    nt = [0] * 960
    nt[0] = 1
    frame = render(c, [(0, 2, 0x20, 4)], nt=nt)
    assert frame[1][4] == BG_PALS[0][1]  # hidden behind opaque BG
    assert frame[1][8] == SPR_PALS[0][2]  # over backdrop: visible
    assert frame[9][4] == SPR_PALS[0][2]  # BG tile ends after row 7


def test_lowest_oam_index_has_priority():
    c = new_chr()
    put_tile(c, 0, 0, solid(1))
    put_tile(c, 0, 1, solid(1))
    oam = [(0, 0, 0x00, 0), (0, 0, 0x01, 0)]
    assert render(c, oam)[1][0] == SPR_PALS[0][1]
    assert render(c, oam[::-1])[1][0] == SPR_PALS[1][1]


def test_behind_bg_sprite_still_masks_lower_priority_sprite():
    c = new_chr()
    put_tile(c, 0, 1, solid(1))
    put_tile(c, 0, 2, solid(2))
    put_tile(c, 0, 3, solid(2))
    put_tile(c, 0, 0, solid(0))
    nt = [0] * 960
    nt[0] = 1
    # Sprite 0 (behind BG, tile 2) hides sprite 1 (front, tile 2 pal 1) at the BG pixel.
    oam = [(0, 2, 0x20, 0), (0, 2, 0x01, 0)]
    assert render(c, oam, nt=nt)[1][0] == BG_PALS[0][1]


def test_8x16_table_selected_by_tile_bit0_and_pair_by_upper_bits():
    c = new_chr()
    put_tile(c, 0, 4, solid(1))  # table 0 pair (4,5) top
    put_tile(c, 0, 5, solid(1))
    put_tile(c, 1, 4, solid(2))  # table 1 pair (4,5)
    put_tile(c, 1, 5, solid(3))  # bottom half of table 1 pair
    even = render(c, [(0, 4, 0, 0)])
    odd = render(c, [(0, 5, 0, 0)])
    assert even[1][0] == SPR_PALS[0][1] and even[16][0] == SPR_PALS[0][1]
    assert odd[1][0] == SPR_PALS[0][2]  # table 1, top tile 4
    assert odd[9][0] == SPR_PALS[0][3]  # table 1, bottom tile 5


# ---------------------------------------------------------------------------
# upload_palette: palette RAM mirroring (Requirements 9.7, 10.4)
# ---------------------------------------------------------------------------

from converter.emitter import palette_arrays  # noqa: E402
from converter.models import PaletteDef, PaletteSet  # noqa: E402
from tests.reference_renderer import upload_palette  # noqa: E402


@pytest.mark.parametrize("sprite_addr,bg_addr", [
    (0x3F10, 0x3F00), (0x3F14, 0x3F04), (0x3F18, 0x3F08), (0x3F1C, 0x3F0C),
])
def test_sprite_color0_write_lands_in_bg_mirror(sprite_addr, bg_addr):
    bg, spr = upload_palette(b"\x21", start=sprite_addr)
    idx = (bg_addr - 0x3F00) // 4
    assert bg[idx][0] == 0x21
    assert spr[idx][0] == 0x21


def test_palette_address_wraps_at_32_bytes():
    bg, _ = upload_palette(b"\x25", start=0x3F20)
    assert bg[0][0] == 0x25


def test_palette_values_masked_to_6_bits():
    bg, _ = upload_palette(b"\xe1\x7f", start=0x3F00)
    assert bg[0][0] == 0x21
    assert bg[0][1] == 0x3F


def test_old_layout_clobbers_backdrop_with_sprite_color0():
    bg_arr = [0x0F] * 16
    spr_arr = [0x01] * 16
    for i, v in zip((0, 4, 8, 12), (0x16, 0x27, 0x30, 0x12)):
        spr_arr[i] = v
    bg, spr = upload_palette(bytes(bg_arr + spr_arr))
    # The sprite writes to $3F10/14/18/1C land last in $3F00/04/08/0C.
    assert [p[0] for p in bg] == [0x16, 0x27, 0x30, 0x12]
    assert [p[0] for p in spr] == [0x16, 0x27, 0x30, 0x12]
    assert bg[0][0] != 0x0F
    # Non-mirrored entries are untouched.
    assert bg[0][1:] == [0x0F] * 3
    assert spr[0][1:] == [0x01] * 3


def _new_layout_set() -> PaletteSet:
    return PaletteSet(
        bg=(PaletteDef("bg0", (1, 2, 3, 4)), PaletteDef("bg1", (1, 5, 6, 7))),
        sprite=(PaletteDef("sp0", (8, 9, 10)),),
        nes_colors={1: 0x21, 2: 0x11, 3: 0x12, 4: 0x13, 5: 0x14, 6: 0x15,
                    7: 0x16, 8: 0x27, 9: 0x28, 10: 0x29},
    )


def test_new_layout_keeps_backdrop_equal_to_common_bg_color():
    bg_arr, spr_arr = palette_arrays(_new_layout_set())
    bg, spr = upload_palette(bytes(bg_arr + spr_arr))
    backdrop = bg_arr[0]
    assert backdrop == 0x21
    assert [p[0] for p in bg] == [backdrop] * 4
    assert [p[0] for p in spr] == [backdrop] * 4
    # Distinct sprite colors still survive in the non-mirrored slots.
    assert spr[0][1:] != bg[0][1:]


def test_render_blank_frame_uses_uploaded_backdrop():
    bg_arr, spr_arr = palette_arrays(_new_layout_set())
    bg, spr = upload_palette(bytes(bg_arr + spr_arr))
    frame = render_nes_frame(bytes(8192), [0] * 960, [0] * 64, bg, spr, [])
    assert len(frame) == 240 and all(len(r) == 256 for r in frame)
    assert {px for row in frame for px in row} == {bg_arr[0]}
