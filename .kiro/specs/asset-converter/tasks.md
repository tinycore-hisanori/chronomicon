# Implementation Plan: Asset Converter

## Overview

The converter is a Python 3 package `converter/` with tests under `tests/` (pytest + Hypothesis), laid out as in the design. Stages are built in pipeline order: scaffolding, Manifest, Pyxres_Loader, Palette_Quantizer, palette_map and screen layouts, CHR_Encoder, Font_Mapper, Nametable_Builder, Attribute_Builder, Metasprite_Builder, Emitter, orchestrator/CLI, then the reference renderer with the fidelity and determinism properties. Each task wires into the previous ones, and the orchestrator in task 14 connects all stages.

## Tasks

- [x] 1. Set up project scaffolding
  - [x] 1.1 Create package skeleton, `errors.py` and `models.py`
    - Create `pyproject.toml` (Python 3.11+, `tomli; python_version < "3.11"`, `pyyaml`, dev extras `pytest`, `hypothesis`, `pyxel` for generating the sample file only)
    - Create `converter/__init__.py`, `converter/data/__init__.py`, `tests/__init__.py`
    - Implement `ConversionError` in `converter/errors.py`
    - Implement all frozen dataclasses of the design's Data Models section in `converter/models.py`, including `Resources` (ordered tuple of `PyxresData` with the first-file-wins lookup helper for banks and tilemaps) and the `cell_uv` helper
    - Include `ObjectDef` (`name`, `x`, `y`, `screen` defaulting to 0) and `ScreenDef.objects` (tuple, default empty)
    - _Requirements: 6.2, 7.9, 7.10, 9.3, 11.2, 14.1_

- [x] 2. Implement the Manifest loader and validator
  - [x] 2.1 Implement `converter/manifest.py`
    - `load_manifest(path)`: read JSON or YAML by extension, build `ManifestData`, resolve `pyxres_files` relative to the Manifest file
    - Fail-fast checks in design order: missing Manifest or `nes_colors` (7.2), empty `bg_palette_regions` (2.8), `screens` entry fields and `count` < 1 (14.3), sprite `w`/`h`/palette (12.2-12.4), C-identifier sprite names, undefined BG palette in a region (13.6)
    - `validate_against_resources(manifest, resources)`: sprite rectangle inside bank (12.6), screen and HUD tilemap numbers exist (14.4)
    - Parse the optional `objects` list of a `screens` entry into `ObjectDef` items (`name`, `x`, `y`, optional `screen`, default 0); absent or empty gives an empty tuple
    - Validate `objects` items: unknown sprite name, `x` or `y` outside 0-255, `screen` outside 0..`count`-1; each message carries the entry position, item position and offending value
    - Error messages carry the context named in the requirements
    - _Requirements: 2.8, 7.2, 9.3, 12.1, 12.2, 12.3, 12.4, 12.6, 13.1, 13.6, 14.1, 14.3, 14.4, 14.6, 14.7, 14.8_

  - [x] 2.2 Write unit tests in `tests/test_manifest.py`
    - One test per Manifest error row, asserting the message contains the required items
    - Valid JSON and YAML Manifests parse to equal `ManifestData`
    - `objects`: absent and empty lists parse to an empty tuple, `screen` defaults to 0
    - One test each for unknown sprite name, `x` or `y` outside 0-255 (256 and -1) and `screen` outside 0..`count`-1, asserting entry position and offending value in the message
    - _Requirements: 2.8, 7.2, 9.3, 12.2, 12.3, 12.4, 12.6, 13.6, 14.1, 14.3, 14.4, 14.6, 14.7, 14.8_

- [x] 3. Implement the Pyxres_Loader
  - [x] 3.1 Implement `converter/pyxres_loader.py`
    - Define the `PYXRES_SCHEMA` constant (archive entry name, key names, max `format_version` 4)
    - `load_pyxres(path)` using `zipfile` and `tomllib` (fallback `tomli`), never importing `pyxel`
    - Expand Pyxel's trailing-repeat compression for image rows, image rows, tilemap rows and tilemap row lists, then fold `(tx, ty)` pairs into cells
    - Raise `ConversionError` for unreadable file, bad zip, malformed TOML, missing entry or key, unsupported version and pixel values outside 0-15 (with path, bank, position, value)
    - _Requirements: 7.1, 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7_

  - [x] 3.2 Implement the test helper `tests/pyxres_writer.py`
    - `write_pyxres(path, images, tilemaps, compress=False)` writing `pyxel_resource.toml` (format_version 1) by hand-serialised TOML
    - With `compress=True` apply Pyxel's trailing-repeat compression
    - _Requirements: 11.8_

  - [x] 3.3 Write property test for the loader round trip
    - **Property 12: Pyxres loader round trip**
    - **Validates: Requirements 11.1, 11.2, 11.8**
    - In `tests/test_pyxres_loader.py`, with compressed and uncompressed archives

  - [x] 3.4 Write unit tests for the loader
    - Add a script that saves a real `tests/data/sample.pyxres` with Pyxel and check the file in; test that it loads with the expected shape
    - One test per error case: missing file, not a zip, bad TOML, missing entry, pixel value 16
    - _Requirements: 7.1, 11.3, 11.4, 11.5, 11.6, 11.7_

- [x] 4. Implement the Palette_Quantizer
  - [x] 4.1 Implement `converter/palette.py`
    - `build_palettes(manifest)` returning `PaletteSet`: `nes_colors` lookup, at most 4 BG and 4 sprite palettes, at most 4 colors per palette, identical color 0 across BG palettes
    - `pyxel_to_nes(palette_set, pyxel_color)` raising on unknown index
    - No RGB estimation and no automatic assignment
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.9, 7.5_

  - [x] 4.2 Write property test for palette limits
    - **Property 2: Palettes never exceed four colors**
    - **Validates: Requirements 2.2, 2.3**
    - In `tests/test_palette.py`

  - [x] 4.3 Write unit tests for palette errors
    - Unknown color index, 5 colors in a palette, 5 palettes, BG color 0 mismatch
    - _Requirements: 2.4, 2.6, 2.7, 2.9_

- [x] 5. Implement palette_map and screen layouts
  - [x] 5.1 Implement `converter/palette_map.py`
    - `bg_palette_of_tile(regions, bank, u, v)`: region lookup, error for no region (13.4) and for conflicting regions (13.5); overlapping regions with the same palette are allowed
    - `build_screen_layouts(manifest, resources, palette_set)`: for each screen (numbered consecutively across entries) collect the 32x30 `TileRef` grid (HUD rows 0-3 from the HUD source, BG rows 4-29 from `(x + 32*i, y + 4)`) and the 32x30 `palette_map`
    - Bounds check for screen and HUD regions with screen index, tilemap number and bounds in the message
    - _Requirements: 3.1, 3.4, 3.5, 13.2, 13.3, 13.4, 13.5, 13.7, 14.2, 14.5_

  - [x] 5.2 Write property test for palette_map consistency
    - **Property 13: palette_map consistency**
    - **Validates: Requirements 13.2, 13.3, 13.8**
    - In `tests/test_palette_map.py`, comparing against a direct rectangle test

  - [x] 5.3 Write unit tests for palette_map and layouts
    - No region, conflicting regions, same-palette overlap accepted
    - Screen numbering across entries, HUD vs BG sources, out-of-bounds error
    - _Requirements: 3.4, 13.4, 13.5, 14.5_

- [x] 6. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Implement the CHR_Encoder
  - [x] 7.1 Implement BG encoding in `converter/chr_encoder.py`
    - `encode_tile` / `decode_tile` (16 bytes, plane 0 then plane 1)
    - `encode_bg_tiles(layouts, resources, palette_set, manifest)`: collect referenced tiles in deterministic order (file order, bank, row-major), check pixel colors against the tile's BG palette, convert to in-palette indices, deduplicate
    - Blank tiles map to slot 0x20; game slots come from 0x00-0x1F then 0x7F-0xFF; never assign 0x20-0x7E
    - Capacity error reports the unique non-blank count against 161
    - _Requirements: 1.1, 1.3, 1.5, 1.7, 1.10, 1.11, 6.2, 7.3_

  - [x] 7.2 Add sprite encoding to `converter/chr_encoder.py`
    - `hflip_pair` and `encode_sprite_tiles(sprite_defs, resources, palette_set)`: cut each `SpriteDef` into 8x16 cells, check colors against the sprite palette, deduplicate pairs including mirrored pairs (record `h_flip`), keep pairs with one blank tile, list fully blank cells in `blank_cells`
    - Upper tile at even slot, lower at the next odd slot; capacity error reports tile count against 256
    - _Requirements: 1.2, 1.4, 1.6, 1.8, 1.9, 1.10, 1.11, 7.4_

  - [x] 7.3 Write property test for the CHR round trip
    - **Property 1: CHR encode/decode round trip**
    - **Validates: Requirements 1.10, 10.3**
    - In `tests/test_chr_encoder.py`, for 8x8 tiles and 8x16 pairs

  - [x] 7.4 Write property test for BG deduplication
    - **Property 7: BG tile deduplication**
    - **Validates: Requirements 1.3, 1.7**

  - [x] 7.5 Write property test for sprite pair deduplication
    - **Property 8: Sprite pair deduplication with flip sharing**
    - **Validates: Requirements 1.8, 1.9**

  - [x] 7.6 Write unit tests for the CHR_Encoder
    - 161 BG tiles succeed and 162 fail with counts in the message; 128 sprite pairs succeed and 129 fail
    - Slots 0x20-0x7E never assigned; OAM tile is `upper | 1`; pair with one blank tile kept; color outside palette error
    - _Requirements: 1.2, 1.3, 1.5, 1.6, 1.8, 1.11_

- [x] 8. Implement bundled font data and the Font_Mapper
  - [x] 8.1 Create `converter/data/pyxel_font.py` and `THIRD_PARTY_NOTICES.md`
    - Extract the 95 glyph bitmaps (ASCII 0x20-0x7E, 4x6) of the Pyxel built-in font from the Pyxel project (https://github.com/kitao/pyxel) as plain Python integers, with no imports
    - Record the origin (project, source file, release used) in the module docstring and in `THIRD_PARTY_NOTICES.md`
    - `THIRD_PARTY_NOTICES.md` contains the full MIT license text; copy the exact copyright line and notice text from the `LICENSE` file of the Pyxel release used for the extraction (do not write it from memory)
    - _Requirements: 8.5, 8.6_

  - [x] 8.2 Implement `converter/font_mapper.py`
    - `encode_font(chr_bytes)`: write each glyph into the slot equal to its ASCII code, glyph in columns 0-3 and rows 0-5, stroke index 3, everything else 0; idempotent
    - `get_pyxel_glyph_pixels(code)` as the independent test reference
    - _Requirements: 1.12, 8.1, 8.2, 8.3, 8.4, 8.5_

  - [x] 8.3 Write property test for the font round trip
    - **Property 10: Font glyph round trip**
    - **Validates: Requirements 8.1, 8.2, 8.4**
    - In `tests/test_font_mapper.py`

  - [x] 8.4 Write unit tests for font and notices
    - All 95 codes checked exhaustively; `THIRD_PARTY_NOTICES.md` exists and contains the MIT permission sentence and the Pyxel project name
    - Importing `converter` with `pyxel` blocked in `sys.modules` succeeds
    - _Requirements: 8.3, 8.5, 8.6_

- [x] 9. Implement the Nametable_Builder
  - [x] 9.1 Implement `converter/nametable.py`
    - `build_nametables(layouts, tile_to_chr_id)`: 960 ids per screen at offset `row * 32 + col`, HUD cells in 0-127 and BG cells in 128-959
    - Error for a missing `(u, v)` in the CHR table (3.7) and for an id outside 0-255 (3.3), with column, row and screen index
    - _Requirements: 3.1, 3.2, 3.3, 3.5, 3.6, 3.7, 7.6_

  - [x] 9.2 Write property test for nametable range
    - **Property 5: Nametable tile ids stay in the CHR range**
    - **Validates: Requirements 3.2, 3.5**
    - In `tests/test_nametable.py`

  - [x] 9.3 Write unit tests for the Nametable_Builder
    - HUD rows from the HUD source and BG rows from `(x + 32*i, y + 4)`; missing `(u, v)` error; id above 255 error
    - _Requirements: 3.1, 3.3, 3.5, 3.7_

- [x] 10. Implement the Attribute_Builder
  - [x] 10.1 Implement `converter/attribute.py`
    - `build_attribute_table(screen_index, palette_map)`: 64 bytes, bits 1:0 top-left, 3:2 top-right, 5:4 bottom-left, 7:6 bottom-right; last block row has bottom bits 0
    - Error for a conflict inside a 16x16 block (block column 0-15, row 0-14, palettes involved) and for a palette number outside 0-3
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 7.7_

  - [x] 10.2 Write property test for attribute range
    - **Property 3: Attribute table entries are in range**
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.5**
    - In `tests/test_attribute.py`, including decode back to block palettes

  - [x] 10.3 Write unit tests for the Attribute_Builder
    - Hand-computed attribute byte, conflict error with block coordinates, palette 4 error
    - _Requirements: 4.2, 4.4, 4.6_

- [x] 11. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 12. Implement the Metasprite_Builder
  - [x] 12.1 Implement `converter/metasprite.py`
    - Decompose each `SpriteDef` into `(w/8) x (h/16)` cells in row-major order with offsets `(8*cx, 16*cy)`
    - OAM tile `upper_slot | 1`; attribute bits 1:0 palette, bit 6 from the stored flip flag; skip cells in `blank_cells`
    - Warn on stderr when one row exceeds 8 hardware sprites, and continue
    - `flip_metasprite(entry, width)`: `x -> width - 8 - x`, toggle bit 6, keep `y` and tile; emit normal then flipped variant per sprite in Manifest order
    - _Requirements: 5.1, 5.3, 5.4, 5.5, 5.6, 12.5_

  - [x] 12.2 Write property test for flip symmetry
    - **Property 4: Metasprite flip symmetry**
    - **Validates: Requirements 5.2**
    - In `tests/test_metasprite.py`

  - [x] 12.3 Write property test for flip involution
    - **Property 14: Metasprite flip involution**
    - **Validates: Requirements 5.5, 5.6**

  - [x] 12.4 Write property test for SpriteDef decomposition
    - **Property 15: SpriteDef decomposition**
    - **Validates: Requirements 12.5**

  - [x] 12.5 Write unit tests for the Metasprite_Builder
    - Empty-cell skip vs one blank tile kept; 9 sprites in a row warns and continues; flipped example `x' = w - 8 - x`
    - _Requirements: 5.3, 5.4, 5.5_

- [x] 13. Implement the Emitter
  - [x] 13.1 Implement `converter/emitter.py`
    - `emit_all(result, out_dir)`: write to a temp directory next to `out_dir` (fall back to the system temp dir), compute byte lengths and CRC-32, create `out_dir` if missing, then `os.replace` each file; remove the temp directory in `finally`; never touch `out_dir` before the final move
    - `chr.bin` always 8192 bytes (BG table then sprite table, zero filled)
    - `assets.h`: palette arrays and `metasprite_<name>` / `metasprite_<name>_flip` in `oam_meta_spr` format, groups of four bytes, terminator `128`, signed offsets written as `(unsigned char)` casts for negatives
    - `nametable_N.s`: ca65 data with 960 nametable bytes, 64 attribute bytes and an objects table ending in `$ff`
    - Objects table for screen index `i` of an entry: the entry's `objects` items whose `screen` equals `i`, in Manifest order, each as `.byte x, y, metasprite_index` (index = position of the SpriteDef in `sprites`), then `.byte $ff`; only `.byte $ff` when there are none
    - The emitter receives the Manifest `screens` and `sprites` order for this purpose; `y` is the display Y (no `-1` correction in the output)
    - _Requirements: 7.8, 9.1, 9.2, 9.3, 9.4, 9.5, 14.9, 14.10, 14.11_

  - [x] 13.2 Write property test for `chr.bin` size
    - **Property 6: `chr.bin` is always 8192 bytes**
    - **Validates: Requirements 9.1, 9.4**
    - In `tests/test_emitter.py`

  - [x] 13.3 Write unit tests for the Emitter
    - `assets.h` snapshot with terminator and negative offsets; `nametable_N.s` snapshot; missing `out_dir` is created
    - Objects table snapshots: no `objects` gives only `.byte $ff`; items on different `screen` indices land in the right file in Manifest order; the metasprite index is the SpriteDef position in `sprites`
    - _Requirements: 9.2, 9.3, 9.5, 14.9, 14.10, 14.11_

- [x] 14. Implement the orchestrator and CLI
  - [x] 14.1 Implement `converter/converter.py`
    - `convert(pyxres_override, manifest_path, out_dir)` running stages in design order: manifest, loader, `validate_against_resources`, palettes, screen layouts, BG CHR, font, sprite CHR, nametables, attribute tables, metasprites, emitter
    - Pass the Manifest `screens` (with `objects`) and `sprites` order to the emitter so the objects tables are written
    - Catch `ConversionError`, print `error: <message>` to stderr, return 1; return 0 on success
    - Log byte length and CRC-32 (hex) of every generated asset, including nametable, attribute, palette and metasprite blocks
    - CLI entry point with `argparse` and a `__main__` guard
    - _Requirements: 6.3, 7.1, 7.8, 7.9, 7.10, 9.5, 14.10_

  - [x] 14.2 Write unit tests in `tests/test_converter.py`
    - Failure injected in an earlier stage and in the emit step leaves `out_dir` contents and mtimes unchanged, removes the temp directory and returns 1
    - A successful run after a failed one replaces the files completely
    - Success log contains length and CRC-32 for each asset
    - _Requirements: 6.3, 7.8, 7.9, 7.10_

- [x] 15. Implement the reference renderer and fidelity tests
  - [x] 15.1 Implement `tests/reference_renderer.py`
    - `render_nes_frame(chr_bin, nametable, attr, bg_palettes, sprite_palettes, oam)` returning 240 rows of 256 NES color bytes: BG pass with attribute lookup, then sprite pass in 8x16 mode in reverse OAM order with flip bits, transparency and behind-background priority
    - `oam` holds raw OAM bytes `(y, tile, attr, x)`; the renderer draws a sprite with OAM Y byte `Y` from screen row `Y + 1` (rows `Y+1 .. Y+16`) like real hardware and clips rows beyond 239
    - Helper `build_oam(metasprite, display_x, display_y)` builds the OAM list from metasprite data at given placements; each hardware sprite becomes `(display_y - 1 + y_offset, oam_tile, attributes, display_x + x_offset)`, with OAM Y in 0-239
    - _Requirements: 10.1_

  - [x] 15.2 Implement the scene generator in `tests/strategies.py`
    - Hypothesis strategy for valid scenes: palettes of at most 4 colors, BG tiles with one region per palette, uniform palette per 16x16 block, sprite images and placements (normal or flipped, at most 8 per scanline), within 161 BG tiles and 128 sprite pairs
    - Writes the scene to `.pyxres` plus Manifest through `write_pyxres`
    - Avoid placements that would need OAM Y = -1 (display Y = 0 with a zero y offset); keep every OAM Y byte in 0-239
    - _Requirements: 10.1, 10.2_

  - [x] 15.3 Write property test for conversion fidelity
    - **Property 11: Conversion fidelity**
    - **Validates: Requirements 10.1, 10.2**
    - In `tests/test_fidelity.py`: compare the Pyxel-side composite mapped through `nes_colors` with `render_nes_frame` of the converter output; also check the transparent sprite color is never drawn
    - Build the OAM list with `build_oam` (OAM Y = `display_y - 1 + y_offset`) and rely on the renderer's `Y + 1` rule so sprites appear at the intended display rows

  - [x] 15.4 Write property test for deterministic conversion
    - **Property 9: Deterministic conversion**
    - **Validates: Requirements 6.1, 6.2**
    - In `tests/test_fidelity.py`: convert twice into two directories and compare `chr.bin`, `assets.h`, every `nametable_N.s` and the file name set

  - [x] 15.5 Write unit tests for the reference renderer
    - In `tests/test_reference_renderer.py`: a sprite with OAM Y = 10 first appears on row 11 and its last row is 26; rows beyond 239 are clipped
    - `build_oam` writes `display_y - 1 + y_offset` as the OAM Y byte
    - _Requirements: 10.1_

- [x] 16. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- All tasks, including property-based tests and unit tests, are required
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate the 15 correctness properties of the design
- Unit tests validate specific examples and error messages
- `check_nes.py` appears in the design layout but is not covered by these requirements, so it has no task here

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["2.1", "3.1", "3.2", "4.1", "8.1", "10.1", "15.1"] },
    { "id": 2, "tasks": ["2.2", "3.3", "4.2", "5.1", "10.2", "15.5"] },
    { "id": 3, "tasks": ["3.4", "4.3", "5.2", "7.1", "10.3"] },
    { "id": 4, "tasks": ["5.3", "7.2", "7.3", "8.2", "9.1"] },
    { "id": 5, "tasks": ["7.4", "8.3", "9.2", "12.1", "13.1"] },
    { "id": 6, "tasks": ["7.5", "8.4", "9.3", "12.2", "13.2", "14.1"] },
    { "id": 7, "tasks": ["7.6", "12.3", "13.3", "14.2", "15.2"] },
    { "id": 8, "tasks": ["12.4", "15.3"] },
    { "id": 9, "tasks": ["12.5", "15.4"] }
  ]
}
```
