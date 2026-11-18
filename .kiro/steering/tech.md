---
inclusion: always
---
# Technical ground rules

## Toolchain
- Python 3 + `pyxel` (source games, asset loading), `pillow`
- `cc65` (cl65 / ca65 / ld65) + **NESLib** (zlib licence) for the runtime
- Headless verification: `nes-py` or our own browser player `tinynes` (Node-compatible `nes.js`)
- Linker config: NROM-256 (PRG 32KB at $8000, CHR 8KB), `oam_off` must be a ZEROPAGE symbol
  defined in C (`#pragma bss-name (push,"ZEROPAGE")`) because NESLib's display.sinc imports it

## Development environment (hard rules)
- Python **3.12**. Always use the project virtual environment at `.venv` in the repo root.
  Run every tool through it: `.venv\Scripts\python -m pytest`, `.venv\Scripts\python -m pip ...`.
  Never use a system or global Python.
- Dependencies are only the ones declared in `pyproject.toml` (runtime and the `dev` extra).
  **Ask the user before `pip install`-ing anything that is not in `pyproject.toml`.**
- The `converter` package uses neither `pyxel` nor `pillow`. `pyxel` is used only by
  `tests/data/make_sample_pyxres.py` (to generate the sample `.pyxres`).
- Tests: `tests/conftest.py` registers Hypothesis profiles `dev` (default, `max_examples=25`)
  and `ci` (`max_examples=200`), selected with the `HYPOTHESIS_PROFILE` environment variable.
  The full suite must finish within 60 seconds with the `dev` profile; check slow tests with
  `.venv\Scripts\python -m pytest --durations=10` and keep generated data small.
## Target hardware limits (the "8-bit subset" a Pyxel game must respect)
| Item | Rule |
|---|---|
| Screen | 256x240, top 32px reserved for HUD |
| Drawing API | only `blt`, `bltm`, `text`, `cls` (no `pset/line/rect/circ/tri/fill/pal/clip/camera`) |
| Background | 8x8 tiles; collision by tile id |
| Colors | per 16x16 BG block one 4-color palette; 4 BG + 4 sprite palettes; sprite = 3 colors + transparent |
| Sprites | 8x16 mode, 64 hardware sprites, max 8 per scanline; keep ≤ 12 objects on screen |
| Math | no `math`/float; positions are 1/16 fixed point ints; sin/cos via lookup tables |
| Sound | 2 pulse + triangle + noise |
| Size | NROM: PRG 32KB / CHR 8KB |
| Scrolling | v1 uses flip-screen (no scrolling) |

A static checker (`check_nes.py`) must reject games that break these rules **before** conversion.

## Known pitfalls (learned the hard way — do not repeat)
1. **NESLib `vram_write(ptr, 0)` writes 64KB**, corrupting palette/VRAM. Never call it with length 0
   (guard empty strings in text helpers).
2. Calling `pad_poll(0)` and `pad_trigger(0)` in the same frame loses edge detection.
   Call `pad_trigger(0)` once per frame, then read held buttons with `pad_state(0)`.
3. Letting the converter auto-pick BG palettes per tile splits walls and floors into different
   palettes → attribute conflicts. Palettes must be fixed per tile in the manifest.
4. Pyxel colors do not map 1:1 to the 2C02 palette; keep an explicit Pyxel→NES color table
   (`nes_colors`) in the manifest instead of nearest-RGB guessing.
5. Text tiles: map Pyxel's built-in font into CHR at ASCII codes so strings can be written
   directly to the nametable; text background is opaque (BG tiles cannot be transparent).
6. cc65: declare variables at block start, prefer `unsigned char`, avoid int multiply/divide in
   hot loops, keep large state in globals (stack is small).
7. Freeing CHR: use 8x16 sprites and skip empty tiles; generate horizontally-flipped metasprites
   instead of duplicating tiles.
8. Mirroring naming: iNES "vertical mirroring" = CIRAM A10 ← PPU A10. Nintendo's own board pads use
   the opposite letters. Our cartridge board labels follow iNES.

## Testing expectations
- Every converter stage gets unit tests; invariants get **property-based tests** (Hypothesis):
  CHR encode/decode round-trip, ≤4 colors per palette after quantisation, attribute table
  consistency, metasprite flip symmetry, nametable values within CHR range.
- End-to-end: build ROM → run scripted input in headless emulator → compare screenshots
  with the Pyxel version (pixel structure, not exact colors).
