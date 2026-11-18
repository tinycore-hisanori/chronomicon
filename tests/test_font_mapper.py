"""Tests for converter.font_mapper."""
from hypothesis import given, strategies as st

from converter.chr_encoder import decode_tile
from converter.font_mapper import encode_font, get_pyxel_glyph_pixels


# Feature: asset-converter, Property 10: Font glyph round trip
# **Validates: Requirements 8.1, 8.2, 8.4**
@given(st.integers(0x20, 0x7E))
def test_font_glyph_round_trip(code):
    chr_bytes = encode_font(bytearray(4096))
    tile = decode_tile(bytes(chr_bytes[code * 16 : code * 16 + 16]))
    assert tile == get_pyxel_glyph_pixels(code)
    assert {v for row in tile for v in row} <= {0, 3}
    for y, row in enumerate(tile):
        assert all(v == 0 for v in row[4:])
        if y >= 6:
            assert all(v == 0 for v in row)

# ---------------------------------------------------------------------------
# Unit tests (Requirements 8.3, 8.5, 8.6)
# ---------------------------------------------------------------------------
import subprocess
import sys
from pathlib import Path

import pytest

from converter.data.pyxel_font import FIRST_CODE, LAST_CODE

REPO_ROOT = Path(__file__).resolve().parent.parent
SENTINEL = 0xAA


def test_all_95_codes_use_slot_equal_to_ascii_code():
    chr_bytes = encode_font(bytearray([SENTINEL]) * 4096)
    assert len(chr_bytes) == 4096
    assert (LAST_CODE - FIRST_CODE + 1) == 95
    for code in range(0x20, 0x7F):
        tile = decode_tile(bytes(chr_bytes[code * 16 : code * 16 + 16]))
        assert tile == get_pyxel_glyph_pixels(code), hex(code)


def test_slots_outside_font_range_are_untouched():
    chr_bytes = encode_font(bytearray([SENTINEL]) * 4096)
    assert bytes(chr_bytes[: 0x20 * 16]) == bytes([SENTINEL]) * (0x20 * 16)
    assert bytes(chr_bytes[0x7F * 16 :]) == bytes([SENTINEL]) * (4096 - 0x7F * 16)


def test_encode_font_is_idempotent_and_in_place():
    buf = bytearray([SENTINEL]) * 4096
    first = bytes(encode_font(buf))
    assert encode_font(buf) is buf
    assert bytes(buf) == first


def test_known_glyph_bytes_exclamation():
    chr_bytes = encode_font(bytearray(4096))
    rows = [0x40, 0x40, 0x40, 0x00, 0x40, 0x00, 0x00, 0x00]
    assert bytes(chr_bytes[0x21 * 16 : 0x21 * 16 + 16]) == bytes(rows + rows)


def test_known_glyph_bytes_capital_a():
    chr_bytes = encode_font(bytearray(4096))
    rows = [0x40, 0xA0, 0xE0, 0xA0, 0xA0, 0x00, 0x00, 0x00]
    assert bytes(chr_bytes[0x41 * 16 : 0x41 * 16 + 16]) == bytes(rows + rows)


def test_space_glyph_is_blank():
    chr_bytes = encode_font(bytearray([SENTINEL]) * 4096)
    assert bytes(chr_bytes[0x20 * 16 : 0x21 * 16]) == bytes(16)


@pytest.mark.parametrize("code", [0x1F, 0x7F])
def test_glyph_pixels_rejects_out_of_range_codes(code):
    with pytest.raises(ValueError):
        get_pyxel_glyph_pixels(code)


@pytest.mark.parametrize("size", [0, 4095, 4097, 8192])
def test_encode_font_rejects_wrong_size_table(size):
    with pytest.raises(ValueError):
        encode_font(bytearray(size))


def test_third_party_notices_contains_mit_text_and_pyxel_reference():
    path = REPO_ROOT / "THIRD_PARTY_NOTICES.md"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "Permission is hereby granted, free of charge" in text
    assert "Pyxel" in text
    assert "https://github.com/kitao/pyxel" in text


def test_converter_imports_without_pyxel_or_pillow():
    code = (
        "import sys, importlib, pkgutil\n"
        "for name in ('pyxel', 'PIL'):\n"
        "    sys.modules[name] = None\n"
        "import converter\n"
        "names = [m.name for m in pkgutil.walk_packages(converter.__path__, 'converter.')\n"
        "         if m.name != 'converter.__main__']\n"
        "for name in names:\n"
        "    importlib.import_module(name)\n"
        "assert 'converter.font_mapper' in names and 'converter.converter' in names\n"
        "assert sys.modules['pyxel'] is None and sys.modules['PIL'] is None\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr

