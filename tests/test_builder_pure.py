"""Pure-Python tests for the rom-builder package (no external tools)."""

from __future__ import annotations

import json

import pytest
from hypothesis import given
from hypothesis import strategies as st

from builder.config import load_build_config, validate_name
from builder.errors import BuildError
from builder.ines import assemble_rom, build_ines_header

CHR_SIZE = 8192


@st.composite
def _rom_inputs(draw):
    prg_kb = draw(st.sampled_from([16, 32]))
    mirroring = draw(st.sampled_from(["vertical", "horizontal"]))
    # Small repeated seeds keep example generation fast; content is still random.
    seed = draw(st.binary(min_size=1, max_size=64))
    prg = (seed * (prg_kb * 1024 // len(seed) + 1))[: prg_kb * 1024]
    chr_seed = draw(st.binary(min_size=1, max_size=64))
    chr_bin = (chr_seed * (CHR_SIZE // len(chr_seed) + 1))[:CHR_SIZE]
    return prg_kb, mirroring, prg, chr_bin


def _check_header(header: bytes, prg_kb: int, mirroring: str) -> None:
    assert len(header) == 16
    assert header[0:4] == b"NES\x1a"
    assert header[4] == prg_kb // 16
    assert header[5] == 1
    assert header[6] & 1 == (1 if mirroring == "vertical" else 0)
    assert header[6] >> 4 == 0  # mapper 0 (low nibble)
    assert header[7] >> 4 == 0  # mapper 0 (high nibble)
    assert header[7:16] == bytes(9)


# Feature: rom-builder, Property 1: iNES header and ROM layout
# Validates: Requirements 1.2, 1.3
@given(_rom_inputs())
def test_property_ines_header_and_rom_layout(args):
    prg_kb, mirroring, prg, chr_bin = args
    header = build_ines_header(prg_kb, mirroring)
    _check_header(header, prg_kb, mirroring)

    rom = assemble_rom(prg, chr_bin, prg_kb, mirroring)
    assert len(rom) == 16 + prg_kb * 1024 + CHR_SIZE
    assert rom[:16] == header
    assert rom[16 : 16 + prg_kb * 1024] == prg
    assert rom[16 + prg_kb * 1024 :] == chr_bin


@pytest.mark.parametrize("prg_kb", [16, 32])
@pytest.mark.parametrize("mirroring", ["vertical", "horizontal"])
def test_header_and_layout_examples(prg_kb, mirroring):
    prg = bytes([0xEA]) * (prg_kb * 1024)
    chr_bin = bytes([0x55]) * CHR_SIZE
    header = build_ines_header(prg_kb, mirroring)
    _check_header(header, prg_kb, mirroring)
    rom = assemble_rom(prg, chr_bin, prg_kb, mirroring)
    assert rom == header + prg + chr_bin
    assert len(rom) == 16 + prg_kb * 1024 + CHR_SIZE


@pytest.mark.parametrize("prg_kb", [0, 8, 24, 64, True, "32"])
def test_header_rejects_bad_prg_kb(prg_kb):
    with pytest.raises(ValueError):
        build_ines_header(prg_kb, "vertical")


@pytest.mark.parametrize("mirroring", ["", "Vertical", "four", None])
def test_header_rejects_bad_mirroring(mirroring):
    with pytest.raises(ValueError):
        build_ines_header(32, mirroring)


def test_assemble_rejects_bad_sizes():
    chr_bin = bytes(CHR_SIZE)
    with pytest.raises(ValueError):
        assemble_rom(bytes(16 * 1024), chr_bin, 32, "vertical")
    with pytest.raises(ValueError):
        assemble_rom(bytes(32 * 1024 - 1), chr_bin, 32, "vertical")
    with pytest.raises(ValueError):
        assemble_rom(bytes(16 * 1024), bytes(CHR_SIZE - 1), 16, "vertical")
    with pytest.raises(ValueError):
        assemble_rom(bytes(16 * 1024), bytes(CHR_SIZE + 1), 16, "vertical")


# ---------------------------------------------------------------------------
# Property 2: Manifest name validation
# ---------------------------------------------------------------------------

_DEVICES = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in "123456789"} | {
    f"LPT{i}" for i in "123456789"
}
_FIRST = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_")
_REST = _FIRST | {".", "-"}


def _expected_valid(name: str) -> bool:
    """Independent re-statement of the design rule (no regex)."""
    if not 1 <= len(name) <= 64:
        return False
    if name[0] not in _FIRST or any(c not in _REST for c in name[1:]):
        return False
    if name.endswith((".", " ")):
        return False
    return name.split(".")[0].upper() not in _DEVICES


# Mostly name-like characters (plus a few troublemakers) so both outcomes are hit often.
_NAME_CHARS = st.sampled_from(sorted(_REST) + [" ", "\n", "/", "\\", "é", "\x00"])
_name_text = st.one_of(
    st.text(_NAME_CHARS, max_size=70),
    st.text(max_size=10),
    st.builds(
        lambda body, tail: body + tail,
        st.text(st.sampled_from(sorted(_FIRST)), min_size=1, max_size=8),
        st.sampled_from(["", "\n", " ", ".", "\r\n"]),
    ),
    st.builds(
        lambda dev, ext, case: (dev.lower() if case else dev) + ext,
        st.sampled_from(sorted(_DEVICES)),
        st.sampled_from(["", ".txt", ".a.b", ".", " "]),
        st.booleans(),
    ),
)


# Feature: rom-builder, Property 2: Manifest name validation
# Validates: Requirements 1.8, 1.9
@given(_name_text)
def test_property_validate_name_matches_rule(name):
    if _expected_valid(name):
        assert validate_name(name) == name
    else:
        with pytest.raises(BuildError) as info:
            validate_name(name)
        assert "name" in str(info.value)


# Feature: rom-builder, Property 2: Manifest name validation
# Validates: Requirements 1.8, 1.9
@given(
    st.one_of(
        st.none(), st.integers(), st.floats(), st.booleans(), st.binary(max_size=8),
        st.lists(st.text(max_size=3), max_size=3),
    )
)
def test_property_validate_name_rejects_non_strings(value):
    with pytest.raises(BuildError) as info:
        validate_name(value)
    assert "name" in str(info.value)


@pytest.mark.parametrize(
    "name", ["game", "_x", "a.b-c", "9lives", "a" * 64, "CON1", "COM10", "console", "nul_x"]
)
def test_validate_name_accepts_examples(name):
    assert validate_name(name) == name


@pytest.mark.parametrize(
    "name",
    ["", ".hidden", "-x", "a b", "a/b", "a" * 65, "x.", "game\n", "con", "Nul.txt", "lpt9.a.b"],
)
def test_validate_name_rejects_examples(name):
    with pytest.raises(BuildError, match="name"):
        validate_name(name)


def _write_manifest(tmp_path, **fields):
    for rel in fields.pop("_files", ["main.c"]):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("")
    data = {"name": "demo", "game_sources": ["main.c"]}
    data.update(fields)
    data = {k: v for k, v in data.items() if v is not _MISSING}
    path = tmp_path / "game.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


_MISSING = object()


def _load(path, tmp_path):
    return load_build_config(path, tmp_path / "build", tmp_path / "runtime")


def test_load_defaults_and_relative_sources(tmp_path):
    path = _write_manifest(
        tmp_path, game_sources=["src/a.c", "b.s"], _files=["src/a.c", "b.s"]
    )
    cfg = _load(path, tmp_path)
    assert cfg.prg_kb == 32 and cfg.mirroring == "vertical"
    assert cfg.name == "demo"
    assert cfg.game_sources == (
        (tmp_path / "src" / "a.c").resolve(),
        (tmp_path / "b.s").resolve(),
    )
    assert cfg.rom_path == tmp_path / "build" / "demo.nes"


def test_load_explicit_values(tmp_path):
    cfg = _load(_write_manifest(tmp_path, prg_kb=16, mirroring="horizontal"), tmp_path)
    assert (cfg.prg_kb, cfg.mirroring, cfg.prg_start) == (16, "horizontal", 0xC000)


@pytest.mark.parametrize(
    "fields, word",
    [
        ({"game_sources": ["missing.c"]}, "game_sources"),
        ({"game_sources": ["main.txt"], "_files": ["main.txt"]}, "game_sources"),
        ({"game_sources": ["main.C"], "_files": ["main.C"]}, "game_sources"),
        (
            {"game_sources": ["a/x.c", "b/x.s"], "_files": ["a/x.c", "b/x.s"]},
            "duplicate",
        ),
        ({"game_sources": []}, "game_sources"),
        ({"game_sources": _MISSING}, "game_sources"),
        ({"prg_kb": 8}, "prg_kb"),
        ({"prg_kb": "32"}, "prg_kb"),
        ({"prg_kb": True}, "prg_kb"),
        ({"mirroring": "four"}, "mirroring"),
        ({"mirroring": ["vertical"]}, "mirroring"),
    ],
)
def test_load_rejects_bad_fields(tmp_path, fields, word):
    with pytest.raises(BuildError, match=word):
        _load(_write_manifest(tmp_path, **fields), tmp_path)


@pytest.mark.parametrize("name", [_MISSING, None, 5, "bad name", "con"])
def test_load_checks_name_first(tmp_path, name):
    path = _write_manifest(
        tmp_path, name=name, game_sources=["nope.txt"], prg_kb=7, mirroring="x"
    )
    with pytest.raises(BuildError) as info:
        _load(path, tmp_path)
    assert "name" in str(info.value)
    assert "game_sources" not in str(info.value)


# ---------------------------------------------------------------------------
# Property 3: PRG overflow detection
# ---------------------------------------------------------------------------

from builder.linkmap import (  # noqa: E402
    Overflow,
    Segment,
    find_overflow,
    parse_labels,
    parse_ld65_overflow,
    parse_segment_list,
)

_PRG_NAMES = ("STARTUP", "CODE", "RODATA", "ONCE", "LOWCODE")
_OTHER_ROWS = (
    ("ZEROPAGE", 0x000000, 0x00000F),
    ("BSS", 0x000300, 0x0003FF),
    ("DATA", 0x000400, 0x00041F),
    ("VECTORS", 0x00FFFA, 0x00FFFF),
)
# (prg_start, prg_size): 32 KB and 16 KB layouts (the 6 vector bytes are excluded).
_PRG_AREAS = [(0x8000, 0x7FFA), (0xC000, 0x3FFA)]


def _render_segment_list(rows) -> str:
    """Render (name, start, end) rows like a real ld65 map file."""
    out = [
        "Modules list:",
        "-------------",
        "crt0.o:",
        "    CODE              Offs=000000  Size=000010  Align=00001  Fill=0000",
        "",
        "",
        "Segment list:",
        "-------------",
        "Name                   Start     End    Size  Align",
        "----------------------------------------------------",
    ]
    for name, start, end in rows:
        out.append(f"{name:<22} {start:06X}  {end:06X}  {end - start + 1:06X}  00001")
    out += ["", "", "Exports list by name:", "---------------------"]
    return "\n".join(out) + "\n"


@st.composite
def _layouts(draw):
    prg_start, prg_size = draw(st.sampled_from(_PRG_AREAS))
    names = draw(st.permutations(_PRG_NAMES))
    names = names[: draw(st.integers(1, len(_PRG_NAMES)))]
    # Mix of small sizes, sizes near the limit, and zero (empty segments).
    size_st = st.one_of(
        st.just(0), st.integers(0, 0x40), st.integers(0, prg_size // 2), st.integers(0, prg_size)
    )
    rows = []
    addr = prg_start
    for name in names:
        addr += draw(st.integers(0, 3))  # alignment gap
        size = draw(size_st)
        rows.append((name, addr, addr + size - 1))
        addr += size
    # Non-PRG rows must never influence the result; put them in any position.
    extras = list(draw(st.permutations(_OTHER_ROWS)))[: draw(st.integers(0, 4))]
    all_rows = draw(st.permutations(rows + extras))
    return prg_start, prg_size, rows, all_rows


def _expected_overflow(prg_rows, prg_start, prg_size):
    """Independent oracle: rows are laid out in ascending address order."""
    limit = prg_start + prg_size
    non_empty = [(n, s, e) for n, s, e in prg_rows if e >= s]
    if not non_empty:
        return None
    top = max(e + 1 for _, _, e in non_empty)
    if top <= limit:
        return None
    for name, _s, e in sorted(non_empty, key=lambda r: r[1]):
        if e + 1 > limit:
            return Overflow(name, top - limit)
    raise AssertionError("unreachable")


# Feature: rom-builder, Property 3: PRG overflow detection
# Validates: Requirements 1.4
@given(_layouts())
def test_property_find_overflow_matches_oracle(layout):
    prg_start, prg_size, prg_rows, all_rows = layout
    segments = parse_segment_list(_render_segment_list(all_rows))
    assert [(s.name, s.start, s.end) for s in segments] == [
        (n, s, e) for n, s, e in all_rows
    ]
    assert all(s.size == s.end - s.start + 1 for s in segments)
    assert find_overflow(segments, prg_start, prg_size) == _expected_overflow(
        prg_rows, prg_start, prg_size
    )


_QUOTES = [("'", "'"), ("\u2018", "\u2019"), ("", ""), ("\u201c", "\u201d")]


# Feature: rom-builder, Property 3: PRG overflow detection
# Validates: Requirements 1.4
@given(
    st.sampled_from(_PRG_NAMES),
    st.integers(1, 0x10000),
    st.sampled_from(_QUOTES),
    st.sampled_from(["", "ld65: Warning: ", "ld65.exe: Warning: cfg:12: "]),
    st.sampled_from(["", "\nld65: Error: more text\n"]),
)
def test_property_parse_ld65_overflow_quote_tolerant(name, n, quotes, prefix, suffix):
    lq, rq = quotes
    text = (
        f"{prefix}Segment {lq}{name}{rq} overflows memory area {lq}PRG{rq} by {n} bytes{suffix}"
    )
    assert parse_ld65_overflow(text) == Overflow(name, n)


def test_parse_ld65_overflow_none_for_other_text():
    assert parse_ld65_overflow("") is None
    assert parse_ld65_overflow("ld65: Error: Cannot open 'x.o'") is None


def test_overflow_measured_ld65_example():
    rows = (
        "STARTUP                008000  00803F  000040  00001\n"
        "CODE                   008040  008095  000056  00001\n"
        "RODATA                 008096  011CD5  009C40  00001\n"
        "BSS                    000300  000310  000011  00001\n"
    )
    text = "Segment list:\n-------------\nName   Start  End  Size  Align\n-----\n" + rows
    segments = parse_segment_list(text)
    assert Segment("RODATA", 0x8096, 0x11CD5, 0x9C40) in segments
    assert find_overflow(segments, 0x8000, 0x7FFA) == Overflow("RODATA", 7388)
    err = "Segment 'RODATA' overflows memory area 'PRG' by 7388 bytes"
    assert parse_ld65_overflow(err) == Overflow("RODATA", 7388)
    assert parse_ld65_overflow(err.replace("'", "\u2018", 1).replace("'", "\u2019", 1)) == Overflow(
        "RODATA", 7388
    )


def test_find_overflow_fits_exactly_and_one_over():
    fits = [Segment("CODE", 0x8000, 0xFFF9, 0x7FFA)]
    assert find_overflow(fits, 0x8000, 0x7FFA) is None
    over = [Segment("CODE", 0x8000, 0xFFFA, 0x7FFB)]
    assert find_overflow(over, 0x8000, 0x7FFA) == Overflow("CODE", 1)
    assert find_overflow([], 0xC000, 0x3FFA) is None


def test_parse_labels_example():
    text = (
        "al 000300 ._pw_cases\n"
        "al 008000 .reset_handler\n"
        "al 00FFFA .__VECTORS_RUN__\n"
        "garbage line\n"
        "\n"
    )
    assert parse_labels(text) == {
        "_pw_cases": 0x300,
        "reset_handler": 0x8000,
        "__VECTORS_RUN__": 0xFFFA,
    }
    assert parse_labels("") == {}


# ---------------------------------------------------------------------------
# Task 2.4: tool discovery, run_tool and glue generation
# Requirements: 1.1, 1.7, 8.1
# ---------------------------------------------------------------------------

import sys  # noqa: E402

import builder.tools as tools_mod  # noqa: E402
from builder.glue import write_glue  # noqa: E402
from builder.tools import find_tools, run_tool  # noqa: E402


def _fake_tree(root, with_lib=True):
    bin_dir = root / "bin"
    bin_dir.mkdir()
    paths = {}
    for name in ("cc65", "ca65", "ld65"):
        p = bin_dir / name
        p.write_bytes(b"")
        paths[name] = str(p)
    if with_lib:
        (root / "lib").mkdir()
        (root / "lib" / "none.lib").write_bytes(b"")
    return paths


def _which_of(paths, missing=None):
    return lambda n: None if n == missing else paths.get(n)


@pytest.mark.parametrize("missing", ["cc65", "ca65", "ld65"])
def test_find_tools_missing_tool(tmp_path, monkeypatch, missing):
    paths = _fake_tree(tmp_path)
    monkeypatch.setattr(tools_mod, "_version_of", lambda _p: "cc65 V2.19")
    with pytest.raises(BuildError) as exc:
        find_tools(which=_which_of(paths, missing), environ={})
    assert missing in str(exc.value)
    assert "never installs" in str(exc.value)


def test_find_tools_missing_none_lib(tmp_path, monkeypatch):
    paths = _fake_tree(tmp_path, with_lib=False)
    monkeypatch.setattr(tools_mod, "_version_of", lambda _p: "cc65 V2.19")
    with pytest.raises(BuildError, match="none.lib"):
        find_tools(which=_which_of(paths), environ={})


def test_find_tools_lib_dir_from_bin_parent(tmp_path, monkeypatch):
    paths = _fake_tree(tmp_path)
    monkeypatch.setattr(tools_mod, "_version_of", lambda _p: "cc65 V2.19")
    found = find_tools(which=_which_of(paths), environ={})
    assert found.lib_dir == (tmp_path / "bin").resolve().parent / "lib"
    assert found.none_lib.name == "none.lib"
    assert found.ld65.name == "ld65"


def test_find_tools_cc65_home_overrides(tmp_path, monkeypatch):
    (tmp_path / "a").mkdir()
    paths = _fake_tree(tmp_path / "a", with_lib=False)
    home = tmp_path / "home"
    (home / "lib").mkdir(parents=True)
    (home / "lib" / "none.lib").write_bytes(b"")
    monkeypatch.setattr(tools_mod, "_version_of", lambda _p: "cc65 V2.19")
    found = find_tools(which=_which_of(paths), environ={"CC65_HOME": str(home)})
    assert found.lib_dir == home / "lib"


def test_find_tools_version_warning(tmp_path, monkeypatch, capsys):
    paths = _fake_tree(tmp_path)
    monkeypatch.setattr(tools_mod, "_version_of", lambda _p: "cc65 V2.18 - Git")
    found = find_tools(which=_which_of(paths), environ={})
    err = capsys.readouterr().err
    assert "warning" in err and "2.19" in err and "2.18" in err
    assert found.cc65.name == "cc65"


def test_find_tools_expected_version_is_silent(tmp_path, monkeypatch, capsys):
    paths = _fake_tree(tmp_path)
    monkeypatch.setattr(tools_mod, "_version_of", lambda _p: "cc65 V2.19 - Git abc")
    find_tools(which=_which_of(paths), environ={})
    assert capsys.readouterr().err == ""


def test_run_tool_success_returns_stdout():
    proc = run_tool([sys.executable, "-c", "print('héllo')"], "demo")
    assert proc.stdout.strip() == "héllo"
    assert proc.returncode == 0


def test_run_tool_failure_names_tool_and_stderr():
    code = "import sys; sys.stderr.write('boom happened'); sys.exit(3)"
    with pytest.raises(BuildError) as exc:
        run_tool([sys.executable, "-c", code], "demo.c")
    msg = str(exc.value)
    assert "python" in msg.lower()
    assert "boom happened" in msg
    assert "demo.c" in msg


_ASSETS_H = (
    "const unsigned char chr_data[] = {0};\n"
    "const unsigned char palette_bg[16] = {0};\n"
    "const unsigned char meta_player_0[] = {0};\n"
    "static const int other = 1;\n"
)


def _glue_dir(tmp_path, numbers):
    (tmp_path / "assets.h").write_text(_ASSETS_H, encoding="utf-8")
    for n in numbers:
        (tmp_path / f"nametable_{n}.s").write_text("; nt\n", encoding="utf-8")
    return tmp_path


def test_write_glue_contents(tmp_path):
    d = _glue_dir(tmp_path, [0, 1])
    info = write_glue(d)
    assert info.screen_count == 2
    assert info.extern_names == ("chr_data", "palette_bg", "meta_player_0")
    assert (d / "assets_data.c").read_text() .count('#include "assets.h"') == 1
    decl = (d / "assets_decl.h").read_text()
    assert "extern const unsigned char chr_data[];" in decl
    assert "extern const unsigned char palette_bg[];" in decl
    assert "extern const unsigned char meta_player_0[];" in decl
    assert "other" not in decl
    s = (d / "screens.s").read_text()
    assert (
        ".import _screen0_nametable, _screen0_attr, _screen1_nametable, _screen1_attr"
        in s
    )
    assert ".export _screen_count, screen_nt_lo, screen_nt_hi, screen_at_lo, screen_at_hi" in s
    assert "_screen_count:  .byte 2" in s
    assert "screen_nt_lo:\n    .byte <_screen0_nametable, <_screen1_nametable" in s
    assert "screen_nt_hi:\n    .byte >_screen0_nametable, >_screen1_nametable" in s
    assert "screen_at_lo:\n    .byte <_screen0_attr, <_screen1_attr" in s
    assert "screen_at_hi:\n    .byte >_screen0_attr, >_screen1_attr" in s


def test_write_glue_deterministic(tmp_path):
    d = _glue_dir(tmp_path, [0, 1, 2])
    names = ("assets_data.c", "assets_decl.h", "screens.s")
    write_glue(d)
    first = [(d / n).read_bytes() for n in names]
    write_glue(d)
    assert [(d / n).read_bytes() for n in names] == first
    assert all(b"\r" not in b for b in first)


def test_write_glue_gap_error(tmp_path):
    d = _glue_dir(tmp_path, [0, 2])
    with pytest.raises(BuildError, match="nametable_1.s"):
        write_glue(d)


def test_write_glue_zero_screens(tmp_path):
    d = _glue_dir(tmp_path, [])
    with pytest.raises(BuildError, match="no screens"):
        write_glue(d)


def test_write_glue_too_many_screens(tmp_path):
    d = _glue_dir(tmp_path, range(256))
    with pytest.raises(BuildError, match="too many screens"):
        write_glue(d)
