"""Boot_Test: the boot ROM renders the reference frame and reacts to Start (Req 11, 10.5).

Runs the ROM built from the boot manifest in tinynes (through Node), compares the first
frames with the asset converter's reference renderer (sprites masked) and checks that
holding Start moves the metasprite from X=64 to X=80.
"""

from __future__ import annotations

from tests.frame_compare import (
    compare_frames,
    parse_assets_palettes,
    read_asm_bytes,
    sprite_mask,
)
from tests.reference_renderer import render_nes_frame, upload_palette
from tests.rom_harness import b64, read_labels  # noqa: F401  (b64/read_labels kept for parity)

START = 8
OAM_X0 = 0x203  # X of the first hardware sprite in the shadow OAM page


def _read(name: str, addr: int, length: int) -> dict:
    return {"name": name, "addr": addr, "len": length}


def test_boot_rom_matches_reference_and_start_moves_sprite(boot_rom, boot_runner):
    assets = boot_rom.assets_dir
    chr_bin = (assets / "chr.bin").read_bytes()
    nt = read_asm_bytes(assets / "nametable_0.s", "_screen0_nametable")
    attr = read_asm_bytes(assets / "nametable_0.s", "_screen0_attr")
    pals = parse_assets_palettes(assets / "assets.h")
    bg_pal, sp_pal = upload_palette(bytes(pals["palette_bg"]) + bytes(pals["palette_sprite"]))
    reference = render_nes_frame(chr_bin, nt, attr, bg_pal, sp_pal, [])
    ref_flat = [v for row in reference for v in row]

    shadow = _read("shadow", 0x200, 0x100)
    steps = boot_runner.run(
        [
            {"frames": 30, "reads": [shadow], "snap": ["index_buffer", "oam"]},
            {"frames": 1, "hold": START},
            # The ROM samples the pad in its main loop after the frame in which Start was
            # held, so the shadow OAM changes during the next frame.
            {"frames": 1, "reads": [shadow]},
            {"frames": 1, "snap": ["oam"]},
        ]
    )
    idle, _hold, held, after = steps

    # Req 11.1-11.8: background pixels equal the reference once sprites are masked.
    # The mask comes from the PPU OAM snapshot (RAM can be mid-rebuild at frame end).
    frame = list(idle.snap["index_buffer"])
    mask = sprite_mask(idle.snap["oam"])
    count, first = compare_frames(frame, ref_flat, mask)
    assert count == 0, f"{count} differing pixels outside sprites; first at (x, y) = {first}"

    # Req 10.5 / 11.9-11.10: the sprite starts at X=64 and moves to 80 after Start.
    assert idle.reads["shadow"][3] == 64, f"ram[0x203] before Start = {idle.reads['shadow'][3]}"
    assert held.reads["shadow"][3] == 80, f"ram[0x203] after Start = {held.reads['shadow'][3]}"
    assert after.snap["oam"][3] == 80, f"PPU oam[3] one frame later = {after.snap['oam'][3]}"
