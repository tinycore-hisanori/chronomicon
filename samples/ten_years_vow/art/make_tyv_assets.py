"""Generate samples/ten_years_vow/ten_years_vow.pyxres with Pyxel.

Usage (needs `pip install pyxel`):  python make_tyv_assets.py [out.pyxres]

All art is drawn here as text grids so it can be regenerated and reviewed.
Grid characters: '.' = palette slot 0 (transparent / backdrop), '1' '2' '3' =
palette slots 1-3. Each grid is drawn with one palette, so every pixel ends up as
a Pyxel color that belongs to the palette the Manifest assigns to that area.

Image bank 0 : background tiles (8x8), one palette per 4-row band:
    tile rows 0-3   bg_stone  (Pyxel 0, 1, 13, 7)   navy / grey / white
    tile rows 4-7   bg_wood   (Pyxel 0, 1, 9, 10)   navy / orange / yellow
    tile rows 8-11  bg_sky    (Pyxel 0, 5, 6, 7)    blue / light blue / white
    tile rows 12-15 bg_red    (Pyxel 0, 1, 8, 15)   navy / red / peach
Image bank 1 : sprites.
Tilemap 0 : the stage, 4 rooms of 32x30 tiles side by side (rows 0-3 unused).
Tilemap 1 : HUD (rows 0-3).
Tilemap 2 : title screen.
"""

from __future__ import annotations

import sys

import pyxel

# --------------------------------------------------------------------------- palettes
PAL = {
    "bg_stone": (0, 1, 13, 7),
    "bg_wood": (0, 1, 9, 10),
    "bg_sky": (0, 5, 6, 7),
    "bg_red": (0, 1, 8, 15),
    "sp_knight": (0, 1, 10, 7),
    "sp_bone": (0, 1, 13, 7),
    "sp_demon": (0, 2, 8, 14),
    "sp_fire": (0, 8, 9, 10),
}
BAND = {"bg_stone": 0, "bg_wood": 4, "bg_sky": 8, "bg_red": 12}


def grid(rows: list[str], w: int, h: int, name: str) -> list[str]:
    assert len(rows) == h, f"{name}: {len(rows)} rows, expected {h}"
    for i, r in enumerate(rows):
        assert len(r) == w, f"{name} row {i}: {len(r)} cols, expected {w}: {r!r}"
        assert set(r) <= set(".123"), f"{name} row {i}: bad char in {r!r}"
    return rows


def put(img, x: int, y: int, rows: list[str], pal: tuple[int, int, int, int]) -> None:
    for j, r in enumerate(rows):
        for i, ch in enumerate(r):
            img.pset(x + i, y + j, pal[".123".index(ch)])


# --------------------------------------------------------------------------- BG tiles
# (name) -> (palette, tile x, tile y, 8x8 grid)
T: dict[str, tuple[str, int, int, list[str]]] = {}


WALL = ["11111111", "1.1.1.1.", "11111111", ".1.1.1.1"]


def on_wall(rows: list[str]) -> list[str]:
    """Fill transparent pixels with the dark wall pattern (palette slot 1 = navy)."""
    return ["".join(WALL[y % 4][x] if c == "." else c for x, c in enumerate(r))
            for y, r in enumerate(rows)]


def tile(name: str, pal: str, tx: int, ty: int, rows: list[str], wall: bool = False) -> None:
    assert BAND[pal] <= ty < BAND[pal] + 4, f"tile {name} outside its palette band"
    rows = grid(rows, 8, 8, name)
    T[name] = (pal, tx, ty, on_wall(rows) if wall else rows)


BLANK = ["........"] * 8
for p in BAND:
    tile(f"blank_{p}", p, 15, BAND[p], BLANK)

# --- stone (slot 1 navy mortar/shadow, 2 grey stone, 3 white highlight)
tile("brick_a", "bg_stone", 1, 0, [
    "33333331",
    "32222221",
    "22222221",
    "11111111",
    "33133333",
    "22132222",
    "22122222",
    "11111111",
])
tile("brick_b", "bg_stone", 2, 0, [
    "33331333",
    "22221322",
    "22221222",
    "11111111",
    "33333331",
    "22222221",
    "22122221",
    "11111111",
])
tile("floor_top", "bg_stone", 3, 0, [
    "33333333",
    "32222223",
    "22222222",
    "12222221",
    "11111111",
    "33133331",
    "22122221",
    "11111111",
])
tile("wall_dark", "bg_stone", 4, 0, [
    "11111111",
    "1.1.1.1.",
    "11111111",
    ".1.1.1.1",
    "11111111",
    "1.1.1.1.",
    "11111111",
    ".1.1.1.1",
])
tile("wall_dark2", "bg_stone", 5, 0, [
    "11111111",
    "1.1.1.1.",
    "111111.1",
    ".1.1..11",
    "1111.111",
    "1.1.1.1.",
    "11111111",
    ".1.1.1.1",
])
tile("pillar_l", "bg_stone", 6, 0, [
    "13322222",
    "13322222",
    "13322222",
    "13322221",
    "13322222",
    "13322222",
    "13322222",
    "13322222",
])
tile("pillar_r", "bg_stone", 7, 0, [
    "22222211",
    "22222211",
    "22222211",
    "12222211",
    "22222211",
    "22222211",
    "22222211",
    "22222211",
])
tile("cap_l", "bg_stone", 6, 1, [
    "33333333",
    "12222222",
    ".1111111",
    "..133222",
    "..133222",
    ".1111111",
    "13333333",
    "13322222",
])
tile("cap_r", "bg_stone", 7, 1, [
    "33333333",
    "22222221",
    "1111111.",
    "222221..",
    "222221..",
    "1111111.",
    "33333331",
    "22222211",
])
tile("hud_line", "bg_stone", 8, 0, [
    "........",
    "........",
    "33333333",
    "22222222",
    "........",
    "11111111",
    "........",
    "........",
])
tile("battle_l", "bg_stone", 9, 0, [
    "333.....",
    "321.....",
    "321.....",
    "3211111.",
    "33333333",
    "32222222",
    "22222222",
    "11111111",
])
tile("battle_r", "bg_stone", 10, 0, [
    "....3331",
    "....3221",
    "....3221",
    ".1113221",
    "33333331",
    "22222221",
    "22222221",
    "11111111",
])
tile("step", "bg_stone", 11, 0, [
    "33333333",
    "32222222",
    "32222222",
    "11111111",
    "........",
    "........",
    "........",
    "........",
])
tile("arch_l", "bg_stone", 12, 0, [
    "......33",
    "....3322",
    "...32211",
    "..3221..",
    ".3221...",
    ".321....",
    "3221....",
    "321.....",
])
tile("arch_r", "bg_stone", 13, 0, [
    "33......",
    "2233....",
    "11223...",
    "..1223..",
    "...1223.",
    "....123.",
    "....1223",
    ".....123",
])
tile("arch_side_l", "bg_stone", 12, 1, ["321....."] * 8)
tile("arch_side_r", "bg_stone", 13, 1, [".....123"] * 8)

# --- wood / fire (slot 1 brown, 2 orange, 3 yellow)
tile("plank_l", "bg_wood", 0, 4, [
    "33333333",
    "22222222",
    "21222221",
    "11111111",
    ".1....1.",
    ".1....1.",
    "........",
    "........",
])
tile("plank_r", "bg_wood", 1, 4, [
    "33333333",
    "22222222",
    "12222212",
    "11111111",
    ".1....1.",
    ".1....1.",
    "........",
    "........",
])
tile("flame_l", "bg_wood", 2, 4, [
    "........",
    ".......3",
    "......33",
    ".....323",
    ".....322",
    "....3223",
    "....3233",
    ".....322",
])
tile("flame_r", "bg_wood", 3, 4, [
    "........",
    "3.......",
    "3.......",
    "33......",
    "233.....",
    "323.....",
    "223.....",
    "23......",
])
tile("torch_l", "bg_wood", 2, 5, [
    "....1111",
    ".....211",
    "......11",
    "......11",
    "......11",
    ".....111",
    "....11..",
    "...11...",
])
tile("torch_r", "bg_wood", 3, 5, [
    "1111....",
    "112.....",
    "11......",
    "11......",
    "11......",
    "111.....",
    "..11....",
    "...11...",
])
tile("door_tl", "bg_wood", 4, 4, [
    "......11",
    "....1122",
    "...12222",
    "..122122",
    ".1221122",
    ".1221122",
    "12211222",
    "12211222",
])
tile("door_tr", "bg_wood", 5, 4, [
    "11......",
    "2211....",
    "22221...",
    "221221..",
    "2211221.",
    "2211221.",
    "22211221",
    "22211221",
])
tile("door_ml", "bg_wood", 4, 5, [
    "12211222",
    "12211222",
    "12211222",
    "12211223",
    "12211233",
    "12211222",
    "12211222",
    "12211222",
])
tile("door_mr", "bg_wood", 5, 5, [
    "22211221",
    "22211221",
    "22211221",
    "22211221",
    "22211221",
    "22211221",
    "22211221",
    "22211221",
])
tile("crate_tl", "bg_wood", 6, 4, [
    "11111111",
    "13333333",
    "132.....",
    "13.2....",
    "13..2...",
    "13...2..",
    "13....2.",
    "13.....2",
])
tile("crate_tr", "bg_wood", 7, 4, [
    "11111111",
    "33333331",
    ".....231",
    "....2.31",
    "...2..31",
    "..2...31",
    ".2....31",
    "2.....31",
])
tile("crate_bl", "bg_wood", 6, 5, [
    "13.....2",
    "13....2.",
    "13...2..",
    "13..2...",
    "13.2....",
    "132.....",
    "12222222",
    "11111111",
])
tile("crate_br", "bg_wood", 7, 5, [
    "2.....31",
    ".2....31",
    "..2...31",
    "...2..31",
    "....2.31",
    ".....231",
    "22222221",
    "11111111",
])

# --- sky (slot 1 dark blue, 2 light blue, 3 white)
tile("sky", "bg_sky", 0, 8, ["11111111"] * 8)
tile("sky_star", "bg_sky", 1, 8, [
    "11111111",
    "11111111",
    "11131111",
    "11111111",
    "11111111",
    "11111121",
    "11111111",
    "11111111",
])
tile("moon_tl", "bg_sky", 2, 8, [
    "11111111",
    "11111133",
    "11113333",
    "11133333",
    "11333332",
    "13333322",
    "13333333",
    "33333333",
])
tile("moon_tr", "bg_sky", 3, 8, [
    "11111111",
    "33111111",
    "33331111",
    "33333111",
    "33333311",
    "33333331",
    "32333331",
    "33333333",
])
tile("moon_bl", "bg_sky", 2, 9, [
    "33333333",
    "33332333",
    "13333333",
    "13333332",
    "11333333",
    "11133333",
    "11113333",
    "11111133",
])
tile("moon_br", "bg_sky", 3, 9, [
    "33333333",
    "33333331",
    "33332331",
    "33333331",
    "33333311",
    "33333111",
    "33331111",
    "33111111",
])
tile("glass_tl", "bg_sky", 4, 8, [
    "11111111",
    "12222221",
    "12222213",
    "12222131",
    "12221311",
    "12213111",
    "12131111",
    "11311111",
])
tile("glass_tr", "bg_sky", 5, 8, [
    "11111111",
    "12222221",
    "31222221",
    "13122221",
    "11312221",
    "11131221",
    "11113121",
    "11111311",
])
tile("glass_bl", "bg_sky", 4, 9, [
    "11311111",
    "12131111",
    "12213111",
    "12221311",
    "12222131",
    "12222213",
    "12222221",
    "11111111",
])
tile("glass_br", "bg_sky", 5, 9, [
    "11111311",
    "11113121",
    "11131221",
    "11312221",
    "13122221",
    "31222221",
    "12222221",
    "11111111",
])
tile("skyline_l", "bg_sky", 6, 8, [
    "11111111",
    "11111111",
    "11111111",
    "11111111",
    "1111...1",
    "111.....",
    "1.......",
    "........",
])
tile("skyline_r", "bg_sky", 7, 8, [
    "11111111",
    "11111111",
    "1..11111",
    "....1111",
    ".....111",
    "......11",
    "........",
    "........",
])

# --- red (slot 1 purple, 2 red, 3 peach)
tile("banner_tl", "bg_red", 0, 12, [
    "11111111",
    "12222222",
    "12222222",
    "12222222",
    "12222223",
    "12222233",
    "12222333",
    "12223322",
])
tile("banner_tr", "bg_red", 1, 12, [
    "11111111",
    "22222221",
    "22222221",
    "22222221",
    "32222221",
    "33222221",
    "33322221",
    "22332221",
])
tile("banner_ml", "bg_red", 0, 13, [
    "12223322",
    "12222333",
    "12222233",
    "12222223",
    "12222222",
    "12222222",
    "12222222",
    "12222222",
])
tile("banner_mr", "bg_red", 1, 13, [
    "22332221",
    "33322221",
    "33222221",
    "32222221",
    "22222221",
    "22222221",
    "22222221",
    "22222221",
])
tile("banner_bl", "bg_red", 0, 14, [
    "12222222",
    "12222222",
    "1222222.",
    "122222..",
    "12222...",
    "1222....",
    "122.....",
    "12......",
])
tile("banner_br", "bg_red", 1, 14, [
    "22222221",
    "22222221",
    ".2222221",
    "..222221",
    "...22221",
    "....2221",
    ".....221",
    "......21",
])
tile("spikes", "bg_red", 2, 12, [
    "...3...3",
    "...3...3",
    "..33..33",
    "..32..32",
    ".332.332",
    ".322.322",
    "3322332.",
    "11111111",
])
tile("spike_base", "bg_red", 2, 13, [
    "11111111",
    "1.1.1.1.",
    "11111111",
    ".1.1.1.1",
    "11111111",
    "1.1.1.1.",
    "11111111",
    ".1.1.1.1",
])
tile("carpet", "bg_red", 3, 12, [
    "33333333",
    "22222222",
    "21212121",
    "22222222",
    "12121212",
    "22222222",
    "11111111",
    "........",
])

for _n, (_p, _x, _y, _r) in list(T.items()):
    if _p in ("bg_wood", "bg_red") and not _n.startswith("blank_") and _n != "spike_base":
        T[_n] = (_p, _x, _y, on_wall(_r))
tile("wall_wood", "bg_wood", 14, 4, WALL * 2)
tile("wall_red", "bg_red", 14, 12, WALL * 2)

# --------------------------------------------------------------------------- sprites
KNIGHT_HEAD = [
    "................",
    ".....111111.....",
    "....12222221....",
    "...1222222221...",
    "..122223333221..",
    "..122233313321..",
    "..122233313331..",
    "..12223333331...",
    "..1222133331....",
    "...12211111.....",
]
KNIGHT_BODY = [
    ".....1333331....",
    "....133333331...",
    "...13313333131..",
    "...13133333131..",
    "...13132223131..",
    "...13133333131..",
    "...1213333312...",
    "....1122222211..",
    "....1333333331..",
    "....1333113331..",
]
KNIGHT_ATTACK_BODY = [
    ".....1333331....",
    "....1333333311..",
    "...133133333331.",
    "...131333331331.",
    "...131322233111.",
    "...131333331....",
    "...121333331....",
    "....1122222211..",
    "....1333333331..",
    "....1333113331..",
]
LEGS_STAND = [
    "....133311333...",
    "....13331.1331..",
    "....13331.1331..",
    "....13331.1331..",
    "....12221.1221..",
    "....13331.1331..",
    "...1333311333...",
    "...111111111....",
    "................",
    "................",
    "................",
    "................",
]
LEGS_WALK1 = [
    "....133311333...",
    "...13331..1331..",
    "...1331....1331.",
    "..1331......131.",
    "..1221......121.",
    "..1331......131.",
    ".13331.....13331",
    ".11111.....11111",
    "................",
    "................",
    "................",
    "................",
]
LEGS_WALK2 = [
    "....133311333...",
    ".....13311331...",
    ".....1331331....",
    ".....1331331....",
    ".....1221221....",
    ".....1331331....",
    "....133313331...",
    "....111111111...",
    "................",
    "................",
    "................",
    "................",
]
LEGS_JUMP = [
    "....133311333...",
    "...133331133331.",
    "...13331..13331.",
    "....1331...1331.",
    "....12221.12221.",
    ".....1111..1111.",
    "................",
    "................",
    "................",
    "................",
    "................",
    "................",
]


def knight(body: list[str], legs: list[str], shift: int = 2) -> list[str]:
    """Stack head + body + legs into 32 rows; `shift` blank rows at the top."""
    rows = ["................"] * shift + KNIGHT_HEAD + body + legs
    rows = rows[:32] + ["................"] * (32 - len(rows))
    return rows


SLASH = [
    "................",
    "................",
    "..........1.....",
    "..........11....",
    ".1111111111331..",
    "133333333333331.",
    "1222222222233331",
    "133333333333331.",
    ".1111111111331..",
    "..........11....",
    "..........1.....",
    "................",
    "................",
    "................",
    "................",
    "................",
]

SKELETON_A = [
    "................",
    "................",
    ".....111111.....",
    "....13333331....",
    "...1333333331...",
    "...1311331131...",
    "...1311331131...",
    "...1333113331...",
    "....13333331....",
    ".....131313.....",
    "......1111......",
    ".......12.......",
    "....11112111....",
    "...1.1122211.1..",
    "..1..11212211.1.",
    "..1..12222221.1.",
    "..3..11212211.3.",
    ".....12222221...",
    "......121211....",
    "......122221....",
    ".......1221.....",
    "......121121....",
    ".....12111121...",
    ".....121..121...",
    ".....121..121...",
    ".....121..121...",
    "....1221..1221..",
    "....1111..1111..",
    "................",
    "................",
    "................",
    "................",
]
SKELETON_B = SKELETON_A[:21] + [
    "......121121....",
    "......121.121...",
    ".....121...121..",
    ".....121...121..",
    "....121.....121.",
    "...1221.....1221",
    "...1111.....1111",
    "................",
    "................",
    "................",
    "................",
]

BAT_A = [
    "................",
    "................",
    "1..............1",
    "11............11",
    "121....11....121",
    "1221..1221..1221",
    "12221123321122 1".replace(" ", "2"),
    ".12222333322221.",
    "..122213312221..",
    "...1221111221...",
    "....11....11....",
    "................",
    "................",
    "................",
    "................",
    "................",
]
BAT_B = [
    "................",
    "................",
    "................",
    "................",
    ".......11.......",
    "......1221......",
    "......2332......",
    "....11333311....",
    "...1222332221...",
    "..122211112221..",
    ".12221....12221.",
    "1221........1221",
    "121..........121",
    "11............11",
    "1..............1",
    "................",
]

DEMON_A = [
    "................................",
    "......1....................1....",
    ".....121..................121...",
    ".....1221................1221...",
    "......1221....111111....1221....",
    ".......12211112222221111221.....",
    "........1222222222222222221.....",
    ".......122223322222233222221....",
    ".......122233132222313322221....",
    ".......122233332222333322221....",
    ".......122222222222222222221....",
    "........1222221111112222221.....",
    "........1222213333331222221.....",
    ".........12222131313222221......",
    "..11......122222222222221....11.",
    ".1221......1122222222211....1221",
    "122221....12221111112221...12221",
    "1222221..1222222222222221.122221",
    "12222221122222222222222221222221",
    ".12222222222233222233222222221..",
    "..1222222222333322333322222221..",
    "...12222222223322223322222221...",
    "....122222222222222222222221....",
    ".....1222222222222222222221.....",
    "......12222221111112222221......",
    "......1222221......1222221......",
    "......122221........122221......",
    ".....1222221........1222221.....",
    ".....1222221........1222221.....",
    "....13333331........13333331....",
    "....11111111........11111111....",
    "................................",
]
DEMON_B = [r.replace("1222221122", "1222222122") for r in DEMON_A]
DEMON_B[8] = ".......122233332222333322221...."
DEMON_B[9] = ".......122233332222333322221...."

HEART = [
    "................",
    "................",
    "................",
    "..11..11........",
    ".1331133........"[:16],
    ".13333331.......",
    ".13332231.......",
    ".13322221.......",
    "..132221........",
    "...1221.........",
    "....11..........",
    "................",
    "................",
    "................",
    "................",
    "................",
]
HEART = [r[:8] for r in HEART]
HEART[4] = ".1331331"
FIREBALL = [
    "........",
    "........",
    "...1....",
    "..121...",
    "..1221..",
    ".12321..",
    ".123321.",
    "12333321",
    "12333321",
    ".123321.",
    "..1221..",
    "...11...",
    "........",
    "........",
    "........",
    "........",
]

# name -> (bank-1 u, v, w, h, palette, grid)
SPRITES: dict[str, tuple[int, int, int, int, str, list[str]]] = {
    "knight_idle": (0, 0, 16, 32, "sp_knight", knight(KNIGHT_BODY, LEGS_STAND)),
    "knight_walk1": (16, 0, 16, 32, "sp_knight", knight(KNIGHT_BODY, LEGS_WALK1)),
    "knight_walk2": (32, 0, 16, 32, "sp_knight", knight(KNIGHT_BODY, LEGS_WALK2)),
    "knight_jump": (48, 0, 16, 32, "sp_knight", knight(KNIGHT_BODY, LEGS_JUMP)),
    "knight_attack": (64, 0, 16, 32, "sp_knight", knight(KNIGHT_ATTACK_BODY, LEGS_STAND)),
    "slash": (80, 0, 16, 16, "sp_fire", SLASH),
    "skeleton_a": (0, 32, 16, 32, "sp_bone", SKELETON_A),
    "skeleton_b": (16, 32, 16, 32, "sp_bone", SKELETON_B),
    "bat_a": (0, 64, 16, 16, "sp_demon", BAT_A),
    "bat_b": (16, 64, 16, 16, "sp_demon", BAT_B),
    "demon_a": (0, 80, 32, 32, "sp_demon", DEMON_A),
    "demon_b": (32, 80, 32, 32, "sp_demon", DEMON_B),
    "heart": (0, 112, 8, 16, "sp_fire", HEART),
    "fireball": (8, 112, 8, 16, "sp_fire", FIREBALL),
}

# --------------------------------------------------------------------------- maps
# Each room is built as a 32x30 grid of tile names (None = blank of that block's
# palette). Rows 0-3 of a room are the HUD and are not used here.
W, H = 32, 30


def new_room(fill: str) -> list[list[str]]:
    return [[fill] * W for _ in range(H)]


def rect(room, x, y, w, h, name):
    for j in range(y, y + h):
        for i in range(x, x + w):
            room[j][i] = name


def block2(room, x, y, names):
    """Place a 2x2 group: names = (tl, tr, bl, br)."""
    room[y][x], room[y][x + 1], room[y + 1][x], room[y + 1][x + 1] = names


def floor(room, y=26):
    rect(room, 0, y, W, 1, "floor_top")
    rect(room, 0, y + 1, W, 3, "brick_a")
    for i in range(0, W, 2):
        room[y + 2][i] = "brick_b"


def ceiling(room):
    rect(room, 0, 4, W, 2, "brick_a")
    for i in range(1, W, 2):
        room[5][i] = "brick_b"


def pillar(room, x, top=6, bottom=25):
    block2(room, x, top, ("cap_l", "cap_r", "pillar_l", "pillar_r"))
    rect(room, x, top + 2, 1, bottom - top - 1, "pillar_l")
    rect(room, x + 1, top + 2, 1, bottom - top - 1, "pillar_r")


def window(room, x, y):
    """4x6 arched window: stone arch (2 rows) + glass 2x2 blocks with sky."""
    block2(room, x, y, ("arch_l", "arch_r", "arch_side_l", "arch_side_r"))
    room[y][x + 2], room[y][x + 3] = "blank_bg_stone", "blank_bg_stone"
    room[y + 1][x + 2], room[y + 1][x + 3] = "blank_bg_stone", "blank_bg_stone"
    block2(room, x, y + 2, ("glass_tl", "glass_tr", "glass_bl", "glass_br"))
    block2(room, x + 2, y + 2, ("sky_star", "sky", "sky", "sky_star"))


def moon_window(room, x, y):
    block2(room, x, y, ("sky", "sky_star", "sky", "sky"))
    block2(room, x + 2, y, ("moon_tl", "moon_tr", "moon_bl", "moon_br"))
    block2(room, x + 4, y, ("sky_star", "sky", "sky", "sky"))
    block2(room, x, y + 2, ("sky", "sky", "sky_star", "sky"))
    block2(room, x + 2, y + 2, ("sky", "sky", "sky", "sky_star"))
    block2(room, x + 4, y + 2, ("sky", "sky_star", "sky", "sky"))


def torch(room, x, y):
    block2(room, x, y, ("flame_l", "flame_r", "torch_l", "torch_r"))


def banner(room, x, y):
    block2(room, x, y, ("banner_tl", "banner_tr", "banner_ml", "banner_mr"))
    block2(room, x, y + 2, ("banner_ml", "banner_mr", "banner_bl", "banner_br"))


def plank(room, x, y, n):
    """n 2x2 plank blocks (planks on the top row, blank below)."""
    for k in range(n):
        block2(room, x + 2 * k, y, ("plank_l", "plank_r", "wall_wood", "wall_wood"))


def crate(room, x, y):
    block2(room, x, y, ("crate_tl", "crate_tr", "crate_bl", "crate_br"))


def door(room, x, y):
    block2(room, x, y, ("door_tl", "door_tr", "door_ml", "door_mr"))
    block2(room, x, y + 2, ("door_ml", "door_mr", "door_ml", "door_mr"))


def room_entrance():
    r = new_room("wall_dark")
    for j in range(6, 26):
        for i in range(W):
            if (i * 7 + j * 3) % 11 == 0:
                r[j][i] = "wall_dark2"
    ceiling(r)
    floor(r)
    door(r, 2, 22)
    torch(r, 6, 14)
    window(r, 10, 8)
    window(r, 18, 8)
    torch(r, 24, 14)
    pillar(r, 28)
    crate(r, 14, 24)
    return r


def room_hall():
    r = new_room("wall_dark")
    ceiling(r)
    floor(r)
    pillar(r, 0)
    banner(r, 6, 8)
    plank(r, 4, 18, 3)
    banner(r, 14, 8)
    plank(r, 14, 14, 2)
    banner(r, 22, 8)
    plank(r, 22, 18, 3)
    pillar(r, 30)
    torch(r, 10, 12)
    torch(r, 26, 12)
    return r


def room_corridor():
    r = new_room("wall_dark")
    for j in range(6, 26):
        for i in range(W):
            if (i * 5 + j * 7) % 13 == 0:
                r[j][i] = "wall_dark2"
    ceiling(r)
    floor(r)
    # spike pit columns 10-21
    for i in range(10, 22, 2):
        block2(r, i, 26, ("spikes", "spikes", "spike_base", "spike_base"))
        block2(r, i, 28, ("spike_base", "spike_base", "spike_base", "spike_base"))
    plank(r, 12, 20, 1)
    plank(r, 18, 16, 1)
    window(r, 4, 10)
    window(r, 24, 10)
    torch(r, 14, 10)
    return r


def room_throne():
    r = new_room("wall_dark")
    ceiling(r)
    floor(r)
    moon_window(r, 12, 8)
    banner(r, 6, 8)
    banner(r, 24, 8)
    pillar(r, 2)
    pillar(r, 28)
    for i in range(4, 28, 2):
        block2(r, i, 24, ("carpet", "carpet", "wall_red", "wall_red"))
    # the carpet row sits on the floor line: put floor below it
    rect(r, 4, 26, 24, 1, "floor_top")
    torch(r, 10, 14)
    torch(r, 20, 14)
    return r


def title_screen():
    r = new_room("sky")
    for j in range(0, H):
        for i in range(W):
            if (i * 11 + j * 5) % 17 == 0:
                r[j][i] = "sky_star"
    block2(r, 24, 4, ("moon_tl", "moon_tr", "moon_bl", "moon_br"))
    # castle silhouette from row 20
    for i in range(0, W, 2):
        block2(r, i, 18, ("skyline_l", "skyline_r", "blank_bg_sky", "blank_bg_sky"))
    for i in range(0, W, 2):
        block2(r, i, 20, ("battle_l", "battle_r", "brick_a", "brick_b"))
    rect(r, 0, 22, W, 8, "brick_a")
    for j in range(22, 30):
        for i in range(j % 2, W, 2):
            r[j][i] = "brick_b"
    door(r, 14, 26)
    window(r, 4, 22)
    window(r, 24, 22)
    # text rows 8-16 are left as sky; the runtime writes the title there
    # (font glyphs draw palette slot 3 = white on the sky palette)
    return r


def hud():
    r = new_room("blank_bg_stone")
    rect(r, 0, 3, W, 1, "hud_line")
    return r


# --------------------------------------------------------------------------- build
def main(out: str) -> None:
    pyxel.init(16, 16, title="make_tyv_assets")
    bg = pyxel.images[0]
    for name, (pal, tx, ty, rows) in T.items():
        put(bg, tx * 8, ty * 8, rows, PAL[pal])

    spr = pyxel.images[1]
    for name, (u, v, w, h, pal, rows) in SPRITES.items():
        put(spr, u, v, grid(rows, w, h, name), PAL[pal])

    def write_room(tm, room, ox, oy=0):
        for j in range(H):
            for i in range(W):
                _, tx, ty, _ = T[room[j][i]]
                tm.pset(ox + i, oy + j, (tx, ty))

    stage = pyxel.tilemaps[0]
    stage.imgsrc = 0
    for k, maker in enumerate((room_entrance, room_hall, room_corridor, room_throne)):
        write_room(stage, maker(), 32 * k)
    hudmap = pyxel.tilemaps[1]
    hudmap.imgsrc = 0
    write_room(hudmap, hud(), 0)
    titlemap = pyxel.tilemaps[2]
    titlemap.imgsrc = 0
    write_room(titlemap, title_screen(), 0)

    pyxel.save(out)
    print(f"wrote {out}: {len(T)} BG tiles, {len(SPRITES)} sprites")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "ten_years_vow.pyxres")
