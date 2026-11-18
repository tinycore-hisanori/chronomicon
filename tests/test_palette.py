"""Tests for converter.palette (Palette_Quantizer)."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from converter.errors import ConversionError
from converter.models import ManifestData, PaletteDef
from converter.palette import build_palettes

# --- Strategies ---

nes_color_tables = st.fixed_dictionaries(
    {i: st.integers(0, 0x3F) for i in range(16)}
)


def _manifest(nes_colors, bg, sprite) -> ManifestData:
    return ManifestData(
        (),
        nes_colors,
        tuple(bg),
        tuple(sprite),
        (),
        (),
        (),
    )


def _palette(name: str, colors) -> PaletteDef:
    return PaletteDef(name=name, pyxel_colors=tuple(colors))


@st.composite
def valid_manifests(draw):
    nes_colors = draw(nes_color_tables)
    # Shared BG color 0: every BG palette starts with Pyxel color 0.
    bg = []
    for i in range(draw(st.integers(1, 4))):
        rest = draw(st.lists(st.integers(0, 15), min_size=0, max_size=3))
        bg.append(_palette(f"bg{i}", [0, *rest]))
    sprite = []
    for i in range(draw(st.integers(0, 4))):
        colors = draw(st.lists(st.integers(0, 15), min_size=1, max_size=4))
        sprite.append(_palette(f"sp{i}", colors))
    return _manifest(nes_colors, bg, sprite)


@st.composite
def too_many_colors_manifests(draw):
    """One palette with 5-8 unique Pyxel colors, all defined in nes_colors."""
    nes_colors = draw(nes_color_tables)
    colors = draw(st.lists(st.integers(1, 15), min_size=5, max_size=8, unique=True))
    kind = draw(st.sampled_from(["bg", "sprite"]))
    bad = _palette("bad", [0, *colors] if kind == "bg" else colors)
    if kind == "bg":
        return _manifest(nes_colors, [bad], [])
    return _manifest(nes_colors, [_palette("bg0", [0, 1])], [bad])


@st.composite
def too_many_palettes_manifests(draw):
    """5-8 otherwise valid palettes of one kind."""
    nes_colors = draw(nes_color_tables)
    n = draw(st.integers(5, 8))
    kind = draw(st.sampled_from(["bg", "sprite"]))
    pals = [_palette(f"p{i}", [0, 1 + i % 3]) for i in range(n)]
    if kind == "bg":
        return _manifest(nes_colors, pals, [])
    return _manifest(nes_colors, [_palette("bg0", [0, 1])], pals)


# --- Property 2 ---


# Feature: asset-converter, Property 2: Palettes never exceed four colors
# Validates: Requirements 2.2, 2.3
@given(valid_manifests())
def test_palettes_never_exceed_four_colors(manifest):
    result = build_palettes(manifest)

    assert len(result.bg) <= 4
    assert len(result.sprite) <= 4
    for palette in (*result.bg, *result.sprite):
        nes_bytes = {result.nes_colors[c] for c in palette.pyxel_colors}
        assert 1 <= len(nes_bytes) <= 4


# Feature: asset-converter, Property 2: Palettes never exceed four colors (rejection)
# Validates: Requirements 2.2, 2.3
@given(too_many_colors_manifests())
def test_more_than_four_colors_is_rejected(manifest):
    with pytest.raises(ConversionError):
        build_palettes(manifest)


# Feature: asset-converter, Property 2: Palettes never exceed four colors (rejection)
# Validates: Requirements 2.2, 2.3
@given(too_many_palettes_manifests())
def test_more_than_four_palettes_is_rejected(manifest):
    with pytest.raises(ConversionError):
        build_palettes(manifest)


# --- Unit tests for palette errors (Requirements 2.4, 2.6, 2.7, 2.9) ---

from converter.models import PaletteSet  # noqa: E402
from converter.palette import pyxel_to_nes  # noqa: E402

_NES = {i: 0x0F + i for i in range(16)}


def test_pyxel_to_nes_returns_mapped_byte():
    palette_set = PaletteSet(bg=(), sprite=(), nes_colors=dict(_NES))
    assert pyxel_to_nes(palette_set, 3) == _NES[3]


def test_pyxel_to_nes_unknown_index_names_the_index():
    palette_set = PaletteSet(bg=(), sprite=(), nes_colors={0: 0x0F})
    with pytest.raises(ConversionError, match="99"):
        pyxel_to_nes(palette_set, 99)


def test_unknown_color_index_in_bg_palette_names_index_and_palette():
    manifest = _manifest({0: 0x0F, 1: 0x21}, [_palette("walls", [0, 1, 7])], [])
    with pytest.raises(ConversionError) as exc:
        build_palettes(manifest)
    message = str(exc.value)
    assert "7" in message
    assert "walls" in message


def test_unknown_color_index_in_sprite_palette_names_index_and_palette():
    manifest = _manifest(
        {0: 0x0F, 1: 0x21},
        [_palette("bg0", [0, 1])],
        [_palette("hero", [1, 12])],
    )
    with pytest.raises(ConversionError) as exc:
        build_palettes(manifest)
    message = str(exc.value)
    assert "12" in message
    assert "hero" in message


def test_five_unique_colors_message_has_palette_name_and_count():
    manifest = _manifest(_NES, [_palette("crowded", [0, 1, 2, 3, 4])], [])
    with pytest.raises(ConversionError) as exc:
        build_palettes(manifest)
    message = str(exc.value)
    assert "crowded" in message
    assert "5" in message


def test_duplicate_pyxel_indices_count_once():
    # Five entries but only four unique colors: accepted.
    manifest = _manifest(_NES, [_palette("dup", [0, 1, 2, 3, 3])], [])
    result = build_palettes(manifest)
    assert len(result.bg) == 1


def test_five_palettes_of_a_kind_message_has_kind_and_count():
    bg = [_palette(f"b{i}", [0, 1]) for i in range(5)]
    with pytest.raises(ConversionError) as exc:
        build_palettes(_manifest(_NES, bg, []))
    message = str(exc.value)
    assert "BG" in message
    assert "5" in message

    sprite = [_palette(f"s{i}", [0, 1]) for i in range(5)]
    with pytest.raises(ConversionError) as exc:
        build_palettes(_manifest(_NES, [_palette("bg0", [0, 1])], sprite))
    message = str(exc.value)
    assert "sprite" in message
    assert "5" in message


def test_bg_color_zero_mismatch_message_has_names_and_values():
    nes = dict(_NES)
    nes[0] = 0x0F
    nes[1] = 0x30
    manifest = _manifest(nes, [_palette("a", [0, 2]), _palette("b", [1, 2])], [])
    with pytest.raises(ConversionError) as exc:
        build_palettes(manifest)
    message = str(exc.value)
    assert "'a'" in message
    assert "'b'" in message
    assert "0x0F" in message
    assert "0x30" in message


def test_valid_manifest_builds_palette_set():
    bg = (_palette("bg0", [0, 1, 2, 3]), _palette("bg1", [0, 4]))
    sprite = (_palette("sp0", [5, 6, 7]),)
    result = build_palettes(_manifest(_NES, bg, sprite))

    assert isinstance(result, PaletteSet)
    assert result.bg == bg
    assert result.sprite == sprite
    assert result.nes_colors == _NES
    assert pyxel_to_nes(result, 6) == _NES[6]


def test_shared_color_zero_accepted_for_different_indices_with_same_nes_byte():
    nes = dict(_NES)
    nes[0] = 0x0F
    nes[8] = 0x0F  # different Pyxel index, same NES byte
    manifest = _manifest(nes, [_palette("a", [0, 1]), _palette("b", [8, 2])], [])
    result = build_palettes(manifest)
    assert [p.name for p in result.bg] == ["a", "b"]
