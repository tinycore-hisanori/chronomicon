"""Tests for converter.metasprite (and the pair-flip primitive it relies on)."""

from hypothesis import given, strategies as st

from converter.chr_encoder import decode_tile, encode_sprite_tiles, hflip_pair
from converter.metasprite import build_metasprites, flip_metasprite
from converter.models import (
    HWSprite,
    MetaspriteEntry,
    ImageBank,
    PaletteDef,
    PaletteSet,
    PyxresData,
    Resources,
    SpriteDef,
)

_tile = st.tuples(*[st.tuples(*[st.integers(0, 3)] * 8)] * 8)
_pair = st.tuples(_tile, _tile)

_BLANK_TILE = ((0,) * 8,) * 8
_PAL_COLORS = (0, 5, 6, 7)  # in-palette index -> Pyxel color


# Feature: asset-converter, Property 4: Metasprite flip symmetry (pair level)
# **Validates: Requirements 5.2**
@given(_pair)
def test_hflip_pair_mirrors_both_tiles(pair):
    flipped = hflip_pair(pair)
    for t in range(2):
        for y in range(8):
            for x in range(8):
                assert flipped[t][y][x] == pair[t][y][7 - x]
    assert hflip_pair(flipped) == pair


@st.composite
def _sprite_images(draw):
    """(w, h, rows of in-palette indices) built from a few base pairs so that blank,
    repeated and mirrored cells all occur."""
    w = draw(st.sampled_from([8, 16, 24]))
    h = draw(st.sampled_from([16, 32]))
    bases = draw(st.lists(_pair, min_size=1, max_size=2))
    blank = (_BLANK_TILE, _BLANK_TILE)
    cells = {}
    for cy in range(h // 16):
        for cx in range(w // 8):
            choice = draw(st.integers(-1, len(bases) - 1))
            pair = blank if choice < 0 else bases[choice]
            if draw(st.booleans()):
                pair = hflip_pair(pair)
            cells[(cx, cy)] = pair
    rows = []
    for y in range(h):
        row = []
        for cx in range(w // 8):
            tile = cells[(cx, y // 16)][(y % 16) // 8]
            row.extend(tile[y % 8])
        rows.append(tuple(row))
    return w, h, tuple(rows)


def _decode_pair(chr_bytes, oam_tile, flip):
    slot = oam_tile & 0xFE
    upper = decode_tile(bytes(chr_bytes[16 * slot : 16 * slot + 16]))
    lower = decode_tile(bytes(chr_bytes[16 * slot + 16 : 16 * slot + 32]))
    rows = [list(r) for r in upper + lower]
    if flip:
        rows = [r[::-1] for r in rows]
    return rows


def _compose(entry, chr_bytes, w, h):
    image = [[0] * w for _ in range(h)]
    for s in entry.hw_sprites:
        pair_rows = _decode_pair(chr_bytes, s.oam_tile, bool(s.attributes & 0x40))
        for y in range(16):
            for x in range(8):
                image[s.y_offset + y][s.x_offset + x] = pair_rows[y][x]
    return image


# Feature: asset-converter, Property 4: Metasprite flip symmetry (metasprite level)
# **Validates: Requirements 5.2**
@given(_sprite_images())
def test_flipped_metasprite_is_mirror_of_normal(sprite):
    w, h, rows = sprite
    u, v = 8, 16  # non-zero origin inside a larger bank
    pixels = [[0] * (u + w) for _ in range(v + h)]
    for y in range(h):
        for x in range(w):
            pixels[v + y][u + x] = _PAL_COLORS[rows[y][x]]
    bank = ImageBank(u + w, v + h, tuple(tuple(r) for r in pixels))
    resources = Resources(files=(PyxresData(images=(bank,), tilemaps=()),))
    palette_set = PaletteSet(bg=(), sprite=(PaletteDef("p", _PAL_COLORS),), nes_colors={})
    sprite_def = SpriteDef("spr", 0, u, v, w, h, "p")

    sprite_chr = encode_sprite_tiles([sprite_def], resources, palette_set)
    table = build_metasprites([sprite_def], sprite_chr, palette_set)
    normal, flipped = table.entries
    assert not normal.is_flip and flipped.is_flip

    normal_img = _compose(normal, sprite_chr.chr_bytes, w, h)
    flipped_img = _compose(flipped, sprite_chr.chr_bytes, w, h)

    assert normal_img == [list(r) for r in rows]
    assert flipped_img == [row[::-1] for row in normal_img]


@st.composite
def _metasprite_entries(draw):
    width = 8 * draw(st.integers(1, 8))
    sprites = draw(
        st.lists(
            st.builds(
                HWSprite,
                x_offset=st.integers(0, width // 8 - 1).map(lambda i: 8 * i),
                y_offset=st.integers(0, 255),
                oam_tile=st.integers(0, 255),
                attributes=st.integers(0, 255),
            ),
            max_size=8,
        )
    )
    return MetaspriteEntry(
        name="m", width=width, hw_sprites=tuple(sprites), is_flip=draw(st.booleans())
    )


# Feature: asset-converter, Property 14: Metasprite flip involution
# **Validates: Requirements 5.5, 5.6**
@given(_metasprite_entries())
def test_flip_metasprite_is_involution(entry):
    flipped = flip_metasprite(entry)
    assert flip_metasprite(flipped) == entry
    assert flipped.is_flip == (not entry.is_flip)
    assert flipped.width == entry.width
    assert len(flipped.hw_sprites) == len(entry.hw_sprites)
    for s, f in zip(entry.hw_sprites, flipped.hw_sprites):
        assert f.x_offset == entry.width - 8 - s.x_offset
        assert f.attributes == s.attributes ^ 0x40
        assert f.y_offset == s.y_offset
        assert f.oam_tile == s.oam_tile


# Feature: asset-converter, Property 14: Metasprite flip involution (build output)
# **Validates: Requirements 5.5, 5.6**
@given(_sprite_images())
def test_build_metasprites_emits_normal_then_flipped(sprite):
    w, h, rows = sprite
    pixels = tuple(tuple(_PAL_COLORS[i] for i in row) for row in rows)
    resources = Resources(files=(PyxresData(images=(ImageBank(w, h, pixels),), tilemaps=()),))
    palette_set = PaletteSet(bg=(), sprite=(PaletteDef("p", _PAL_COLORS),), nes_colors={})
    defs = [SpriteDef("a", 0, 0, 0, w, h, "p"), SpriteDef("b", 0, 0, 0, w, h, "p")]
    sprite_chr = encode_sprite_tiles(defs, resources, palette_set)
    table = build_metasprites(defs, sprite_chr, palette_set)
    assert len(table.entries) == 4
    for i in (0, 2):
        normal, flipped = table.entries[i], table.entries[i + 1]
        assert not normal.is_flip and flipped.is_flip
        assert flipped == flip_metasprite(normal)


@st.composite
def _decomposition_sprites(draw):
    """(w, h, blank flags per cell, bank pixels, u, v); non-blank cells hold one lit pixel."""
    w = draw(st.sampled_from(range(8, 65, 8)))
    h = draw(st.sampled_from(range(16, 65, 16)))
    u = draw(st.sampled_from([0, 8, 16]))
    v = draw(st.sampled_from([0, 16]))
    cols, rows = w // 8, h // 16
    blank = {(cx, cy): draw(st.booleans()) for cy in range(rows) for cx in range(cols)}
    pixels = [[0] * (u + w) for _ in range(v + h)]
    for (cx, cy), is_blank in blank.items():
        if not is_blank:
            px = draw(st.integers(0, 7))
            py = draw(st.integers(0, 15))
            pixels[v + 16 * cy + py][u + 8 * cx + px] = _PAL_COLORS[draw(st.integers(1, 3))]
    return w, h, u, v, blank, tuple(tuple(r) for r in pixels)


# Feature: asset-converter, Property 15: SpriteDef decomposition
# **Validates: Requirements 12.5**
@given(_decomposition_sprites())
def test_spritedef_decomposes_into_non_blank_cells_row_major(sprite):
    w, h, u, v, blank, pixels = sprite
    bank = ImageBank(u + w, v + h, pixels)
    resources = Resources(files=(PyxresData(images=(bank,), tilemaps=()),))
    palette_set = PaletteSet(bg=(), sprite=(PaletteDef("p", _PAL_COLORS),), nes_colors={})
    sprite_def = SpriteDef("spr", 0, u, v, w, h, "p")

    sprite_chr = encode_sprite_tiles([sprite_def], resources, palette_set)
    normal = build_metasprites([sprite_def], sprite_chr, palette_set).entries[0]

    cols, rows = w // 8, h // 16
    expected = [
        (8 * cx, 16 * cy)
        for cy in range(rows)
        for cx in range(cols)
        if not blank[(cx, cy)]
    ]
    assert [(s.x_offset, s.y_offset) for s in normal.hw_sprites] == expected
    assert len(normal.hw_sprites) == cols * rows - sum(blank.values())
    assert all(s.oam_tile % 2 == 1 for s in normal.hw_sprites)


# --- Unit tests (Requirements 5.3, 5.4, 5.5) ---

_PAL_B_COLORS = (0, 8, 9, 10)


def _build(sprites, palettes=(("p", _PAL_COLORS),)):
    """sprites: [(name, w, h, palette_name, color, lit pixels [(x, y)])], laid out at (0, 0)
    in separate banks-worth of space: each sprite uses its own image bank."""
    banks = []
    defs = []
    for i, (name, w, h, pal, color, lit) in enumerate(sprites):
        pixels = [[0] * w for _ in range(h)]
        for x, y in lit:
            pixels[y][x] = color
        banks.append(ImageBank(w, h, tuple(tuple(r) for r in pixels)))
        defs.append(SpriteDef(name, i, 0, 0, w, h, pal))
    resources = Resources(files=(PyxresData(images=tuple(banks), tilemaps=()),))
    palette_set = PaletteSet(
        bg=(), sprite=tuple(PaletteDef(n, c) for n, c in palettes), nes_colors={}
    )
    sprite_chr = encode_sprite_tiles(defs, resources, palette_set)
    return build_metasprites(defs, sprite_chr, palette_set)


def test_fully_blank_cell_is_skipped():
    # 16x16: left cell blank, right cell lit.
    table = _build([("s", 16, 16, "p", 5, [(9, 3)])])
    normal = table.entries[0]
    assert [(s.x_offset, s.y_offset) for s in normal.hw_sprites] == [(8, 0)]


def test_cell_with_only_one_blank_tile_is_kept():
    # Only the lower 8x8 tile of the cell has a lit pixel.
    upper_blank = _build([("s", 8, 16, "p", 5, [(2, 12)])]).entries[0]
    assert len(upper_blank.hw_sprites) == 1
    lower_blank = _build([("s", 8, 16, "p", 5, [(2, 1)])]).entries[0]
    assert len(lower_blank.hw_sprites) == 1


def test_nine_sprites_in_a_row_warns_and_continues(capsys):
    lit = [(8 * i, 0) for i in range(9)]
    table = _build([("wide", 72, 16, "p", 5, lit)])
    err = capsys.readouterr().err
    assert "wide" in err and "9" in err
    assert len(table.entries) == 2
    assert len(table.entries[0].hw_sprites) == 9


def test_eight_sprites_in_a_row_does_not_warn(capsys):
    lit = [(8 * i, 0) for i in range(8)]
    table = _build([("ok", 64, 16, "p", 5, lit)])
    assert capsys.readouterr().err == ""
    assert len(table.entries[0].hw_sprites) == 8


def test_flipped_16x16_example():
    # Distinct cells so both are kept: x=0 cell has pixel at col 1, x=8 cell at col 2.
    table = _build([("s", 16, 16, "p", 5, [(1, 0), (10, 5)])])
    normal, flipped = table.entries
    assert [(s.x_offset, s.y_offset) for s in normal.hw_sprites] == [(0, 0), (8, 0)]
    assert [(s.x_offset, s.y_offset) for s in flipped.hw_sprites] == [(8, 0), (0, 0)]
    for n, f in zip(normal.hw_sprites, flipped.hw_sprites):
        assert f.oam_tile == n.oam_tile
        assert f.y_offset == n.y_offset
        assert f.attributes == n.attributes ^ 0x40


def test_flipped_24_wide_example():
    table = _build([("s", 24, 16, "p", 5, [(1, 0), (10, 5), (20, 9)])])
    normal, flipped = table.entries
    assert [s.x_offset for s in normal.hw_sprites] == [0, 8, 16]
    assert [s.x_offset for s in flipped.hw_sprites] == [16, 8, 0]
    assert flipped.width == 24 and flipped.is_flip


def test_attribute_palette_bits_match_sprite_palette_index():
    table = _build(
        [
            ("a", 8, 16, "p", 5, [(1, 1)]),
            ("b", 8, 16, "q", 9, [(1, 1)]),
        ],
        palettes=(("p", _PAL_COLORS), ("q", _PAL_B_COLORS)),
    )
    a_n, a_f, b_n, b_f = table.entries
    assert a_n.hw_sprites[0].attributes & 0x03 == 0
    assert a_f.hw_sprites[0].attributes & 0x03 == 0
    assert b_n.hw_sprites[0].attributes & 0x03 == 1
    assert b_f.hw_sprites[0].attributes & 0x03 == 1


def test_mirrored_cell_sets_flip_bit_in_normal_and_clears_it_in_flipped():
    # Cell 0 has a pixel at col 1; cell 1 is its mirror (col 6) -> stored as h_flip pair.
    table = _build([("s", 16, 16, "p", 5, [(1, 2), (14, 2)])])
    normal, flipped = table.entries
    first, second = normal.hw_sprites
    assert first.oam_tile == second.oam_tile
    assert first.attributes & 0x40 == 0
    assert second.attributes & 0x40 == 0x40
    f_by_x = {s.x_offset: s for s in flipped.hw_sprites}
    assert f_by_x[8].attributes & 0x40 == 0x40  # was cell 0 (unflipped) -> flipped
    assert f_by_x[0].attributes & 0x40 == 0  # was cell 1 (mirrored) -> cleared
