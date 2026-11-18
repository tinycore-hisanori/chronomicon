"""Tests for converter.attribute (Attribute_Builder)."""

from hypothesis import given
from hypothesis import strategies as st

from converter.attribute import BLOCK_COLS, BLOCK_ROWS, build_attribute_table


@st.composite
def block_uniform_palette_maps(draw):
    """Return (32x30 palette map, 15x16 block palettes)."""
    blocks = draw(
        st.lists(
            st.lists(st.integers(0, 3), min_size=BLOCK_COLS, max_size=BLOCK_COLS),
            min_size=BLOCK_ROWS,
            max_size=BLOCK_ROWS,
        )
    )
    cells = [[blocks[y // 2][x // 2] for x in range(32)] for y in range(30)]
    return cells, blocks


# Feature: asset-converter, Property 3: Attribute table entries are in range
# **Validates: Requirements 4.1, 4.2, 4.3, 4.5**
@given(block_uniform_palette_maps())
def test_attribute_table_entries_in_range_and_decode(data):
    cells, blocks = data
    table = build_attribute_table(0, cells)

    assert len(table.data) == 64

    for ay in range(8):
        for ax in range(8):
            byte = table.data[ay * 8 + ax]
            fields = [(byte >> s) & 3 for s in (0, 2, 4, 6)]
            assert all(0 <= f <= 3 for f in fields)
            tl, tr, bl, br = fields
            assert tl == blocks[2 * ay][2 * ax]
            assert tr == blocks[2 * ay][2 * ax + 1]
            if 2 * ay + 1 < BLOCK_ROWS:
                assert bl == blocks[2 * ay + 1][2 * ax]
                assert br == blocks[2 * ay + 1][2 * ax + 1]
            else:
                assert bl == 0 and br == 0


# ---------------------------------------------------------------------------
# Unit tests (Requirements 4.2, 4.4, 4.6)
# ---------------------------------------------------------------------------

import pytest

from converter.errors import ConversionError


def _blank_map(value=0):
    return [[value] * 32 for _ in range(30)]


def _set_block(cells, bx, by, value):
    for dy in (0, 1):
        for dx in (0, 1):
            cells[2 * by + dy][2 * bx + dx] = value


def test_attribute_byte_hand_computed():
    cells = _blank_map()
    _set_block(cells, 0, 0, 1)  # TL
    _set_block(cells, 1, 0, 2)  # TR
    _set_block(cells, 0, 1, 3)  # BL
    _set_block(cells, 1, 1, 0)  # BR
    table = build_attribute_table(5, cells)
    assert table.screen_index == 5
    assert len(table.data) == 64
    assert table.data[0] == 0b00_11_10_01
    assert all(b == 0 for b in table.data[1:])


def test_last_block_row_has_zero_bottom_bits():
    cells = _blank_map()
    for bx in range(16):
        _set_block(cells, bx, 14, 3)
    table = build_attribute_table(0, cells)
    for ax in range(8):
        assert table.data[7 * 8 + ax] == 0b00_00_11_11


def test_conflict_error_reports_block_and_palettes():
    cells = _blank_map()
    cells[2 * 14 + 1][2 * 15 + 1] = 2  # block (column 15, row 14) mixes 0 and 2
    with pytest.raises(ConversionError) as exc:
        build_attribute_table(3, cells)
    msg = str(exc.value)
    assert "column 15" in msg and "row 14" in msg
    assert "[0, 2]" in msg


def test_conflict_error_first_block():
    cells = _blank_map(1)
    cells[1][0] = 3
    with pytest.raises(ConversionError) as exc:
        build_attribute_table(0, cells)
    msg = str(exc.value)
    assert "column 0" in msg and "row 0" in msg
    assert "[1, 3]" in msg


@pytest.mark.parametrize("bad", [4, -1])
def test_out_of_range_palette_error(bad):
    cells = _blank_map()
    cells[7][9] = bad
    with pytest.raises(ConversionError) as exc:
        build_attribute_table(0, cells)
    msg = str(exc.value)
    assert str(bad) in msg
    assert "column 9" in msg and "row 7" in msg


def test_wrong_size_map_error():
    with pytest.raises(ConversionError):
        build_attribute_table(0, [[0] * 32 for _ in range(29)])
    with pytest.raises(ConversionError):
        build_attribute_table(0, [[0] * 31 for _ in range(30)])
    with pytest.raises(ConversionError):
        build_attribute_table(0, [])
