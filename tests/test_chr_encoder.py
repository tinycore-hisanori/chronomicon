"""Tests for converter.chr_encoder."""

from hypothesis import given, strategies as st

from converter.chr_encoder import decode_tile, encode_tile

tiles = st.tuples(
    *[st.tuples(*[st.integers(0, 3)] * 8)] * 8
)


# Feature: asset-converter, Property 1: CHR encode/decode round trip
# **Validates: Requirements 1.10, 10.3**
@given(tiles)
def test_tile_round_trip(tile):
    data = encode_tile(tile)
    assert len(data) == 16
    assert decode_tile(data) == tile


# Feature: asset-converter, Property 1: CHR encode/decode round trip (8x16 pair)
# **Validates: Requirements 1.10, 10.3**
@given(tiles, tiles)
def test_tile_pair_round_trip(top, bottom):
    data = encode_tile(top) + encode_tile(bottom)
    assert len(data) == 32
    assert (decode_tile(data[:16]), decode_tile(data[16:])) == (top, bottom)


def test_known_tile_exact_bytes():
    # Row 0: 0,1,2,3,0,1,2,3 ; row 1: all 3 ; remaining rows 0.
    row0 = (0, 1, 2, 3, 0, 1, 2, 3)
    tile = (row0, (3,) * 8) + ((0,) * 8,) * 6
    expected = bytes([0b01010101, 0xFF, 0, 0, 0, 0, 0, 0,
                      0b00110011, 0xFF, 0, 0, 0, 0, 0, 0])
    assert encode_tile(tile) == expected
    # Leftmost pixel maps to bit 7 of plane 0.
    single = ((1,) + (0,) * 7,) + ((0,) * 8,) * 7
    assert encode_tile(single)[0] == 0x80


# --- Property 7: BG tile deduplication ---

from converter.chr_encoder import BG_GAME_SLOTS, BLANK_SLOT, encode_bg_tiles
from converter.models import (
    ImageBank,
    ManifestData,
    PaletteDef,
    PaletteSet,
    PyxresData,
    Resources,
    ScreenLayout,
    TileRef,
)

_BLANK = ((0,) * 8,) * 8
_POOL_TILES = st.one_of(
    st.sampled_from(
        [
            _BLANK,
            ((1,) * 8,) * 8,
            ((2,) * 8,) * 8,
            tuple(tuple((x + y) % 2 * 3 for x in range(8)) for y in range(8)),
        ]
    ),
    tiles,
)


@st.composite
def _bg_case(draw):
    pool = draw(st.lists(_POOL_TILES, min_size=1, max_size=8))
    # One image bank, tiles side by side in a single 8-px-high strip.
    pixels = tuple(
        tuple(t[y][x] for t in pool for x in range(8)) for y in range(8)
    )
    bank = ImageBank(width=8 * len(pool), height=8, pixels=pixels)
    refs = [TileRef(0, 8 * i, 0) for i in range(len(pool))]
    n_screens = draw(st.integers(1, 2))
    layouts = []
    for s in range(n_screens):
        used = draw(st.lists(st.sampled_from(refs), min_size=1, max_size=6))
        rows = tuple(
            tuple(used[(r * 32 + c) % len(used)] for c in range(32)) for r in range(30)
        )
        layouts.append(
            ScreenLayout(
                screen_index=s, tiles=rows, palette_map=((0,) * 32,) * 30
            )
        )
    return pool, bank, layouts


# Feature: asset-converter, Property 7: BG tile deduplication
# **Validates: Requirements 1.3, 1.7**
@given(_bg_case())
def test_bg_tile_deduplication(case):
    pool, bank, layouts = case
    resources = Resources(files=(PyxresData(images=(bank,), tilemaps=()),))
    palette_set = PaletteSet(
        bg=(PaletteDef("bg0", (0, 1, 2, 3)),), sprite=(), nes_colors={}
    )
    manifest = ManifestData(
        pyxres_files=(),
        nes_colors={},
        bg_palettes=palette_set.bg,
        sprite_palettes=(),
        bg_palette_regions=(),
        sprites=(),
        screens=(),
    )
    result = encode_bg_tiles(layouts, resources, palette_set, manifest)

    def tile_of(ref):
        return pool[ref.u // 8]

    used = {ref for lay in layouts for row in lay.tiles for ref in row}
    # Deterministic encoder order: bank, v, u.
    ordered = sorted(used, key=lambda r: (r.bank, r.v, r.u))
    unique = []
    for ref in ordered:
        t = tile_of(ref)
        if t != _BLANK and t not in unique:
            unique.append(t)

    assert result.num_game_tiles == len(unique)
    assert set(result.tile_to_chr_id) == used

    slot_of = {t: BG_GAME_SLOTS[i] for i, t in enumerate(unique)}
    for ref, chr_id in result.tile_to_chr_id.items():
        t = tile_of(ref)
        if t == _BLANK:
            assert chr_id == BLANK_SLOT
        else:
            assert chr_id == slot_of[t]
            assert not 0x21 <= chr_id <= 0x7E
            assert decode_tile(bytes(result.chr_bytes[chr_id * 16 : chr_id * 16 + 16])) == t

    # Identical tiles share an id; distinct tiles get distinct ids.
    for a in used:
        for b in used:
            assert (tile_of(a) == tile_of(b)) == (
                result.tile_to_chr_id[a] == result.tile_to_chr_id[b]
            )
    game_ids = sorted(i for i in result.tile_to_chr_id.values() if i != BLANK_SLOT)
    assert set(game_ids) == set(BG_GAME_SLOTS[: len(unique)])


# --- Property 8: sprite pair deduplication with flip sharing ---

from converter.chr_encoder import hflip_pair, oam_tile, encode_sprite_tiles
from converter.models import SpriteDef

_SPRITE_TILES = st.one_of(
    st.sampled_from([_BLANK, ((1,) * 8,) * 8, ((3,) * 8,) * 8]),
    tiles,
)


def _mirror_tile(t):
    return tuple(tuple(reversed(row)) for row in t)


@st.composite
def _sprite_case(draw):
    base = draw(
        st.lists(st.tuples(_SPRITE_TILES, _SPRITE_TILES), min_size=1, max_size=5)
    )
    # Always include a fully blank pair and a one-blank-tile pair.
    base = base + [(_BLANK, _BLANK), (_BLANK, ((1,) + (0,) * 7,) * 8)]
    cells = []
    for _ in range(draw(st.integers(1, 10))):
        pair = draw(st.sampled_from(base))
        if draw(st.booleans()):
            pair = hflip_pair(pair)
        cells.append(pair)
    return cells


# Feature: asset-converter, Property 8: Sprite pair deduplication with flip sharing
# **Validates: Requirements 1.8, 1.9**
@given(_sprite_case())
def test_sprite_pair_dedup_with_flip_sharing(cells):
    n = len(cells)
    # One 8x16 cell per column; sprite i occupies columns [8i, 8i+8).
    pixels = tuple(
        tuple(
            (cells[i][0] if y < 8 else cells[i][1])[y % 8][x]
            for i in range(n)
            for x in range(8)
        )
        for y in range(16)
    )
    bank = ImageBank(width=8 * n, height=16, pixels=pixels)
    resources = Resources(files=(PyxresData(images=(bank,), tilemaps=()),))
    palette_set = PaletteSet(
        bg=(), sprite=(PaletteDef("sp0", (0, 1, 2, 3)),), nes_colors={}
    )
    sprite_defs = [SpriteDef(f"s{i}", 0, 8 * i, 0, 8, 16, "sp0") for i in range(n)]

    result = encode_sprite_tiles(sprite_defs, resources, palette_set)

    blank_pair = (_BLANK, _BLANK)
    non_blank = [c for c in cells if c != blank_pair]
    classes = {min(c, hflip_pair(c)) for c in non_blank}
    stored = {e.pair_index for e in result.cell_map.values()}
    assert stored == set(range(len(classes)))

    for i, pair in enumerate(cells):
        key = (f"s{i}", 0, 0)
        if pair == blank_pair:
            assert key in result.blank_cells
            assert key not in result.cell_map
            continue
        assert key not in result.blank_cells
        entry = result.cell_map[key]  # one-blank-tile pairs are kept
        base = 32 * entry.pair_index
        upper = decode_tile(bytes(result.chr_bytes[base : base + 16]))
        lower = decode_tile(bytes(result.chr_bytes[base + 16 : base + 32]))
        stored_pair = (upper, lower)
        if entry.h_flip:
            stored_pair = hflip_pair(stored_pair)
        assert stored_pair == pair
        assert (2 * entry.pair_index) % 2 == 0
        assert oam_tile(entry.pair_index) % 2 == 1


# --- Task 7.6: capacity limits, slot layout, blank handling, foreign colors ---

import pytest

from converter.chr_encoder import BG_CAPACITY
from converter.errors import ConversionError

_PAL = PaletteSet(
    bg=(PaletteDef("bg0", (0, 1, 2, 3)),),
    sprite=(PaletteDef("sp0", (0, 1, 2, 3)),),
    nes_colors={},
)


def _int_tile(n):
    """Unique non-blank tile: n (1..255) in base 4 across the left half of row 0."""
    row = tuple((n >> (2 * i)) & 3 for i in range(4)) + (0,) * 4
    return (row,) + ((0,) * 8,) * 7


def _override(pixels, color_override):
    if color_override is None:
        return pixels
    x, y, color = color_override
    row = list(pixels[y])
    row[x] = color
    return pixels[:y] + (tuple(row),) + pixels[y + 1 :]


def _bg_encode(tile_list, color_override=None):
    """Encode a strip bank of 8x8 tiles, all placed on one 32x30 screen."""
    n = len(tile_list)
    pixels = tuple(tuple(p for t in tile_list for p in t[y]) for y in range(8))
    pixels = _override(pixels, color_override)
    bank = ImageBank(width=8 * n, height=8, pixels=pixels)
    refs = [TileRef(0, 8 * i, 0) for i in range(n)]
    cells = [refs[i % n] for i in range(32 * 30)]
    rows = tuple(tuple(cells[r * 32 : (r + 1) * 32]) for r in range(30))
    layout = ScreenLayout(screen_index=0, tiles=rows, palette_map=((0,) * 32,) * 30)
    resources = Resources(files=(PyxresData(images=(bank,), tilemaps=()),))
    manifest = ManifestData(
        pyxres_files=(), nes_colors={}, bg_palettes=_PAL.bg, sprite_palettes=(),
        bg_palette_regions=(), sprites=(), screens=(),
    )
    return encode_bg_tiles([layout], resources, _PAL, manifest), refs


def _sprite_encode(pair_list, color_override=None):
    """One 8x16 sprite per (upper, lower) pair, laid out side by side."""
    n = len(pair_list)
    pixels = tuple(
        tuple(p for pr in pair_list for p in (pr[0] if y < 8 else pr[1])[y % 8])
        for y in range(16)
    )
    pixels = _override(pixels, color_override)
    bank = ImageBank(width=8 * n, height=16, pixels=pixels)
    resources = Resources(files=(PyxresData(images=(bank,), tilemaps=()),))
    defs = [SpriteDef(f"s{i}", 0, 8 * i, 0, 8, 16, "sp0") for i in range(n)]
    return encode_sprite_tiles(defs, resources, _PAL)


def test_bg_161_unique_tiles_succeed_and_use_exact_slots():
    result, _ = _bg_encode([_int_tile(i + 1) for i in range(BG_CAPACITY)])
    assert BG_CAPACITY == 161
    assert result.num_game_tiles == 161
    ids = set(result.tile_to_chr_id.values())
    assert ids == set(range(0x00, 0x20)) | set(range(0x7F, 0x100))
    assert not any(0x20 <= i <= 0x7E for i in ids)


def test_bg_162_unique_tiles_fail_with_counts():
    with pytest.raises(ConversionError) as exc:
        _bg_encode([_int_tile(i + 1) for i in range(BG_CAPACITY + 1)])
    assert "162" in str(exc.value)
    assert "161" in str(exc.value)


def test_bg_blank_tile_maps_to_0x20_and_uses_no_game_slot():
    result, refs = _bg_encode([_BLANK, _int_tile(1)])
    assert result.tile_to_chr_id[refs[0]] == 0x20
    assert result.tile_to_chr_id[refs[1]] == BG_GAME_SLOTS[0]
    assert result.num_game_tiles == 1


def test_sprite_128_pairs_succeed():
    result = _sprite_encode([(_int_tile(i + 1), _BLANK) for i in range(128)])
    assert {e.pair_index for e in result.cell_map.values()} == set(range(128))
    assert not any(e.h_flip for e in result.cell_map.values())


def test_sprite_129_pairs_fail_with_tile_counts():
    with pytest.raises(ConversionError) as exc:
        _sprite_encode([(_int_tile(i + 1), _BLANK) for i in range(129)])
    assert "258" in str(exc.value)
    assert "256" in str(exc.value)


def test_oam_tile_is_upper_slot_or_one():
    for p in range(128):
        assert oam_tile(p) == 2 * p + 1
        assert oam_tile(p) == (2 * p) | 1


def test_sprite_pair_with_one_blank_tile_is_kept():
    result = _sprite_encode([(_BLANK, _int_tile(1)), (_int_tile(2), _BLANK)])
    assert result.blank_cells == frozenset()
    assert set(result.cell_map) == {("s0", 0, 0), ("s1", 0, 0)}


def test_bg_color_outside_palette_is_reported():
    with pytest.raises(ConversionError) as exc:
        _bg_encode([_int_tile(1), _int_tile(2)], color_override=(8 + 3, 2, 5))
    msg = str(exc.value)
    assert "bank 0" in msg and "u=8" in msg and "v=0" in msg
    assert "color 5" in msg
    assert "bg0" in msg


def test_sprite_color_outside_palette_is_reported():
    # Pixel y=9 lies in the lower tile of the second sprite -> tile at u=8, v=8.
    with pytest.raises(ConversionError) as exc:
        _sprite_encode(
            [(_int_tile(1), _BLANK), (_int_tile(2), _BLANK)], color_override=(8 + 3, 9, 7)
        )
    msg = str(exc.value)
    assert "bank 0" in msg and "u=8" in msg and "v=8" in msg
    assert "color 7" in msg
    assert "sp0" in msg
