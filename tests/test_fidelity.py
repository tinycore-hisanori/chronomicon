"""Property test: the converted screens render like the Pyxel-side composite."""

from __future__ import annotations

import contextlib
import io
import tempfile
from pathlib import Path

from hypothesis import given

from converter.converter import convert, run_pipeline
from converter.emitter import DEFAULT_SPRITE_COLOR, _common_bg_color, _palette_bytes
from tests.reference_renderer import build_oam, render_nes_frame
from tests.strategies import valid_scenes, write_scene


def _palettes(result):
    ps = result.palette_set
    bg = _palette_bytes(ps.bg, ps.nes_colors, _common_bg_color(ps))
    spr = _palette_bytes(ps.sprite, ps.nes_colors, DEFAULT_SPRITE_COLOR)
    return [bg[i : i + 4] for i in range(0, 16, 4)], [spr[i : i + 4] for i in range(0, 16, 4)]


def _oam_for(scene, result, screen):
    entries = {(e.name, e.is_flip): e for e in result.metasprites.entries}
    oam = []
    for p in scene.placements_on(screen):
        oam.extend(build_oam(entries[(p.name, p.flipped)], p.x, p.y))
    return oam


# Feature: asset-converter, Property 11: Conversion fidelity
# **Validates: Requirements 10.1, 10.2**
@given(scene=valid_scenes())
def test_conversion_fidelity(scene):
    with tempfile.TemporaryDirectory() as tmp:
        manifest_path = write_scene(scene, tmp)
        result, _emit = run_pipeline(None, manifest_path, tmp + "/out")

    bg_pal, sp_pal = _palettes(result)
    by_screen = {n.screen_index: n for n in result.nametables}
    attrs = {a.screen_index: a for a in result.attr_tables}
    assert scene.num_screens == len(result.nametables)

    for screen in range(scene.num_screens):
        nt, at = by_screen[screen], attrs[screen]
        oam = _oam_for(scene, result, screen)
        frame = render_nes_frame(result.chr_bin, nt.tile_ids, at.data, bg_pal, sp_pal, oam)

        expected = scene.expected[screen]
        for y in range(240):
            for x in range(256):
                want = scene.nes_colors[expected[y][x]]
                assert frame[y][x] == want, (
                    f"screen {screen} pixel ({x},{y}): expected pyxel color "
                    f"{expected[y][x]} -> NES 0x{want:02x}, rendered 0x{frame[y][x]:02x}"
                )

        # Transparent sprite pixels must leave the background untouched.
        bg_only = render_nes_frame(result.chr_bin, nt.tile_ids, at.data, bg_pal, sp_pal, [])
        sp_defs = {s["name"]: s for s in scene.manifest["sprites"]}
        sp_colors = scene.manifest["sprite_palettes"]
        # Pixels covered by an opaque pixel of ANY sprite (earlier or later in OAM)
        # legitimately differ, so compute coverage over all placements first.
        covered = [[False] * 256 for _ in range(240)]
        for p in scene.placements_on(screen):
            img = scene.sprite_images[p.name]
            if p.flipped:
                img = tuple(tuple(reversed(r)) for r in img)
            transparent = sp_colors[sp_defs[p.name]["palette"]][0]
            for dy, row in enumerate(img):
                for dx, color in enumerate(row):
                    if color != transparent:
                        covered[p.y + dy][p.x + dx] = True
        for p in scene.placements_on(screen):
            img = scene.sprite_images[p.name]
            if p.flipped:
                img = tuple(tuple(reversed(r)) for r in img)
            transparent = sp_colors[sp_defs[p.name]["palette"]][0]
            for dy, row in enumerate(img):
                for dx, color in enumerate(row):
                    px, py = p.x + dx, p.y + dy
                    if color == transparent and not covered[py][px]:
                        assert frame[py][px] == bg_only[py][px], (
                            f"screen {screen} pixel ({px},{py}): transparent sprite pixel "
                            f"changed BG 0x{bg_only[py][px]:02x} to 0x{frame[py][px]:02x}"
                        )


def _convert_quiet(manifest_path, out_dir) -> int:
    with contextlib.redirect_stdout(io.StringIO()):
        return convert(None, manifest_path, out_dir)


def _read_outputs(out_dir: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(out_dir.iterdir()) if p.is_file()}


# Feature: asset-converter, Property 9: Deterministic conversion
# **Validates: Requirements 6.1, 6.2**
@given(scene=valid_scenes())
def test_deterministic_conversion(scene):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        m_a = write_scene(scene, root / "in_a")
        m_b = write_scene(scene, root / "in_b")
        m_c = write_scene(scene, root / "in_c", compress=True)

        runs = {
            "a": (m_a, root / "out_a"),
            "b": (m_b, root / "out_b"),  # identical input bytes, other directory
            "a2": (m_a, root / "out_a2"),  # same input directory converted again
            "c": (m_c, root / "out_c"),  # compressed .pyxres, equivalent content
        }
        for manifest_path, out_dir in runs.values():
            assert _convert_quiet(manifest_path, out_dir) == 0
        outputs = {k: _read_outputs(out) for k, (_m, out) in runs.items()}

        ref = outputs["a"]
        assert "chr.bin" in ref and "assets.h" in ref
        assert any(n.startswith("nametable_") and n.endswith(".s") for n in ref)
        for key in ("b", "a2", "c"):
            assert sorted(outputs[key]) == sorted(ref), key
            for name, data in ref.items():
                assert outputs[key][name] == data, f"{key}: {name} differs"

        # No absolute paths or temp-directory fragments in generated output.
        needles = {tmp, tmp.replace("\\", "/"), str(root.name)}
        for name, data in ref.items():
            for needle in needles:
                assert needle.encode() not in data, f"{name} contains {needle!r}"
