# Requirements Document

## Introduction

This document defines the requirements for the "asset conversion" module (pipeline step 2) of Chronomicon.
The module reads a Pyxel `.pyxres` file (image banks and tilemaps) together with a Manifest, and deterministically produces the set of NES-format assets usable by an iNES mapper 0 (NROM) ROM.

The module covers the following:

1. **Pyxres loading**: reading image banks and tilemaps from a `.pyxres` archive without the Pyxel engine
2. **Manifest schema**: sprite definitions, BG palette regions and screen definitions
3. **CHR data**: 2bpp encoding of 8x8 BG tiles and 8x16 sprite tiles
4. **Nametables**: BG tile layout for 256x240 screens (HUD rows and BG rows from separate sources)
5. **Attribute tables**: per-16x16-block BG palette selection, built from a per-screen `palette_map`
6. **Palettes**: 4 BG palettes + 4 sprite palettes, 4 colors each
7. **Metasprites**: collections of 8x16 hardware sprites in `oam_meta_spr` format, with normal and horizontally flipped variants
8. **Output files**: `chr.bin`, `assets.h` and `nametable_N.s`, written atomically

---

## Glossary

- **Converter**: The whole asset conversion module.
- **Pyxres_Loader**: The sub-component that reads a `.pyxres` file (a zip archive containing TOML) without importing or running the Pyxel engine, and returns image banks and tilemaps.
- **CHR_Encoder**: The sub-component that converts Pyxel tile images into NES 2bpp format.
- **Palette_Quantizer**: The sub-component that maps Pyxel colors to NES 2C02 palette bytes through the Manifest.
- **Nametable_Builder**: The sub-component that builds NES nametables from tilemap regions.
- **Attribute_Builder**: The sub-component that builds NES attribute tables from a `palette_map`.
- **Metasprite_Builder**: The sub-component that builds NES 8x16 metasprites from `SpriteDef` entries.
- **Font_Mapper**: The sub-component that maps the bundled Pyxel built-in font into CHR at ASCII code positions.
- **Emitter**: The sub-component that writes output files, using a temporary directory and an atomic move.
- **Manifest**: A JSON/YAML conversion settings file (fixed palettes, the `nes_colors` table, `sprites`, `bg_palette_regions`, `screens`, and so on).
- **pyxres**: The Pyxel resource file format. A zip archive containing TOML data for image banks, tilemaps and sounds.
- **Image bank**: A Pyxel image bank, a 2D array of Pyxel color indices (0-15).
- **Tilemap**: A Pyxel tilemap, a 2D array of cells, each referencing an image-bank tile coordinate.
- **Pyxel tile coordinate**: The (u, v) pair giving the position of a tile on an image bank. The tile's top-left pixel position, in pixels.
- **2bpp**: The NES CHR encoding that represents a color index with 2 bits per pixel.
- **Nametable**: An array of 32x30 tile IDs referenced by the NES PPU (960 bytes per screen).
- **Attribute table**: An array of 8x8 entries referenced by the NES PPU. Each entry (1 byte) stores four 2-bit palette numbers.
- **Metasprite**: A structure that treats several 8x16 hardware sprites as one game object.
- **SpriteDef**: A Manifest `sprites` entry with the fields `name`, `image_bank`, `u`, `v`, `w`, `h` and `palette`. It describes a w x h pixel rectangle of an image bank that becomes one metasprite, using the sprite palette named by `palette`.
- **bg_palette_regions**: A Manifest list of entries (`image_bank`, `u`, `v`, `w`, `h` -> BG palette name). Each entry assigns one BG palette to every image tile whose top-left pixel position lies inside the rectangle.
- **palette_map**: A 32x30 array of BG palette numbers (0-3), one per screen, with one value per 8x8 nametable cell. The Converter builds it from the tilemap and `bg_palette_regions` and passes it to the Attribute_Builder.
- **screens**: A Manifest list of screen definitions. Each entry has `tilemap` (tilemap number), `x` and `y` (start position in tiles), `count` (screen count N), a HUD source and an optional `objects` list.
- **objects**: An optional list in a `screens` entry. Each item places one metasprite at its initial position and has `name` (SpriteDef name), `x`, `y` (display position in pixels, 0-255) and an optional `screen` (0-based screen index inside the entry, default 0). The `y` value is a display Y; the runtime subtracts 1 from it when writing the OAM Y byte, because the PPU draws a sprite one row below its OAM Y byte.
- **Objects table**: The per-screen table in `nametable_N.s` made of 3-byte items (x, y, metasprite index) followed by the terminator byte $ff.
- **HUD source**: The part of a `screens` entry (`hud_tilemap`, `hud_x`, `hud_y`) that points to a 4-row x 32-column tilemap region. This region supplies the HUD rows (0-3) of each screen of that entry.
- **HUD area**: The top 32 px of the screen (4 tile rows, rows 0-3). It is filled from the HUD source.
- **BG area**: Rows 4-29 of the screen. It is filled from the screen's tilemap region.
- **CHR range**: The valid tile ID range 0-255 (the 8KB CHR holds 512 tiles, split into 256 for BG and 256 for sprites).
- **nes_colors**: A Manifest table that maps a Pyxel color index to an NES 2C02 palette byte.
- **In-palette index**: The order number (0-3) of a color within a palette definition. Distinct from the Pyxel color index (0-15).
- **Background pattern table**: The CHR area $0000-$0FFF (up to 256 tiles = 4096 bytes). It stores BG tiles.
- **Sprite pattern table**: The CHR area $1000-$1FFF (up to 256 tiles = 4096 bytes). It stores sprite tiles.
- **Common background color**: The single NES 2C02 palette byte that is color 0 of all four NES BG palettes.
- **Palette mirror**: The NES PPU palette RAM behavior in which addresses $3F10, $3F14, $3F18 and $3F1C are hardware mirrors of $3F00, $3F04, $3F08 and $3F0C. A write to one of the sprite addresses lands in the corresponding backdrop-side address, so byte 0 of each sprite palette overwrites the backdrop color when the 32 palette bytes are uploaded in one go starting at $3F00.
- **8x16 sprite pair**: The upper tile and lower tile of one NES 8x16 sprite. Deduplication and flip sharing treat the pair as one unit.
- **oam_meta_spr format**: The metasprite data format read by NESLib `oam_meta_spr`. It is a sequence of 4-byte groups (x_offset, y_offset, tile, attr), terminated by the single byte 128. The x_offset and y_offset values are signed bytes.
- **Flip symmetry**: The property that drawing with the horizontal flip flag gives the same result as a pixel-wise mirrored copy of the original tile.
- **Conversion fidelity**: The property that re-rendering the converted output in the NES PPU manner gives the same NES color byte at every pixel as the original Pyxel image converted through `nes_colors`.
- **Third-party notices file**: The repository file `THIRD_PARTY_NOTICES.md`, which records the origin and license text of bundled third-party material.

---

## Requirements

### Requirement 1: CHR Encoding

**User Story:** As a Pyxel developer, I want to convert the tile images of a `.pyxres` file into NES 2bpp CHR format, so that the NES PPU can draw backgrounds and sprites.

#### Acceptance Criteria

1. WHEN image banks are provided by the Pyxres_Loader, THE CHR_Encoder SHALL cut each image tile referenced by a tilemap cell into 8x8 pixels, convert each pixel's Pyxel color index (0-15) to an in-palette index (0-3) using the BG palette that `bg_palette_regions` assigns to that tile, and encode each tile as 16 bytes of NES CHR data (bitplane 0 followed by bitplane 1).
2. WHEN sprite tiles are provided, THE CHR_Encoder SHALL place each 8x16 sprite in the sprite pattern table as two consecutive 8x8 tiles: an even tile index (upper tile) and the next odd tile index (lower tile). In NES 8x16 mode, bit 0 of the OAM tile number field selects the pattern table. Because sprites are placed in the $1000 table, the value written to OAM is "upper tile number (even) | 1". The PPU masks bit 0 of this value to get the upper tile number (value & 0xFE), adds 1 for the lower tile, and draws both from the $1000 table.
3. THE CHR_Encoder SHALL keep the number of game BG tiles stored in the background pattern table within 161 slots (slots 0x00-0x1F and 0x7F-0xFF). The 95 slots 0x20-0x7E are permanently occupied by font glyphs.
4. THE CHR_Encoder SHALL keep the number of tiles stored in the sprite pattern table within 256 tiles (4096 bytes).
5. IF the encoded game BG tile count exceeds 161 slots, THEN THE Converter SHALL abort the conversion, write an error message containing the table kind (BG), the actual tile count and the limit (161 slots) to standard error, and produce no output files.
6. IF the encoded sprite tile count exceeds 256 tiles, THEN THE Converter SHALL abort the conversion, write an error message containing the table kind (sprite), the actual tile count and the limit (256 tiles) to standard error, and produce no output files.
7. THE CHR_Encoder SHALL NOT store BG tiles whose 8x8 in-palette index arrays are identical more than once in CHR. A blank tile (all 16 bytes of its 8x8 in-palette indices equal to 0) SHALL share the font glyph slot for ASCII 0x20 (space) and consume no additional CHR slot for game BG tiles.
8. THE CHR_Encoder SHALL deduplicate sprite tiles per 8x16 sprite pair, and SHALL NOT store pairs with identical in-palette index arrays more than once in CHR. A pair SHALL NOT be removed even if one of its two tiles has all in-palette indices equal to 0.
9. WHEN the horizontally mirrored in-palette index array of a sprite pair (both the upper and lower tile mirrored) matches an existing CHR sprite pair, THE CHR_Encoder SHALL NOT store a new CHR tile for that pair, and SHALL record the index of the matching pair together with a horizontal flip flag (true) as metadata. This sharing applies to sprite tiles only, because the NES PPU cannot flip background tiles.
10. WHEN valid CHR data and its metadata (deduplication mapping and flip flags) are decoded, THE CHR_Encoder SHALL produce in-palette index arrays that equal those of every tile of the original tile images (encode/decode round-trip).
11. IF a pixel of a tile uses a Pyxel color index that is not contained in the palette assigned to that tile, THEN THE CHR_Encoder SHALL abort the conversion, write an error message containing the tile coordinates, the Pyxel color index used and the assigned palette name to standard error, and produce no CHR file. The assigned palette SHALL be the BG palette given by `bg_palette_regions` for a BG tile, and the sprite palette given by the `palette` field of the `SpriteDef` for a sprite tile.
12. WHEN the Font_Mapper stores font glyphs in CHR, THE Font_Mapper SHALL store each glyph as 16 bytes of 2bpp CHR data in the CHR slot whose number equals its ASCII code, for the range ASCII 0x20-0x7E (95 glyphs).

---

### Requirement 2: Palette Quantization

**User Story:** As a Pyxel developer, I want Pyxel colors mapped exactly to the NES 2C02 palette, so that the intended colors are reproduced on the NES.

#### Acceptance Criteria

1. THE Palette_Quantizer SHALL map Pyxel color indices to NES 2C02 palette bytes by looking up the `nes_colors` table in the Manifest (no automatic estimation by RGB approximation).
2. THE Converter SHALL generate at most 4 BG palettes and at most 4 sprite palettes.
3. THE Palette_Quantizer SHALL keep the number of unique colors in each palette within 4.
4. WHEN the number of unique colors of any palette exceeds 4 after quantization, THE Converter SHALL write an error message containing the identifier of the offending palette and its actual color count to standard error, abort the conversion, and produce no output files.
5. THE Palette_Quantizer SHALL read the BG palette assignment from the fixed `bg_palette_regions` setting in the Manifest, and SHALL NOT assign palettes to tiles automatically (this prevents attribute conflicts).
6. IF a Pyxel color index that is not contained in the `nes_colors` table of the Manifest is referenced, THEN THE Palette_Quantizer SHALL write an error message containing that index value to standard error, abort the conversion, and produce no output files.
7. IF the number of BG palettes exceeds 4 or the number of sprite palettes exceeds 4, THEN THE Converter SHALL write an error message containing the offending palette kind and the actual palette count to standard error, abort the conversion, and produce no output files.
8. IF the Manifest defines no BG palette assignment (`bg_palette_regions` is missing or empty), THEN THE Palette_Quantizer SHALL write an error message stating this to standard error, abort the conversion, and produce no output files.
9. IF color 0 of the four BG palettes specified in the Manifest are not identical to each other, THEN THE Palette_Quantizer SHALL write an error message containing the identifiers of the mismatching palettes and their color 0 values to standard error, abort the conversion, and produce no output files.

---

### Requirement 3: Nametable Construction

**User Story:** As a Pyxel developer, I want to convert tilemap regions into NES nametables, so that the NES PPU can draw 256x240 background screens correctly.

#### Acceptance Criteria

1. WHEN a `screens` entry with screen count N is provided, THE Nametable_Builder SHALL generate, for each screen index i from 0 to N-1 (counted from 0 within the entry and numbered consecutively across entries in Manifest order), an array of 32x30 tile IDs (960 bytes). The BG area (rows 4-29) of screen i SHALL be read from the 32-column x 26-row region of the entry's tilemap that starts at tile position (x + 32*i, y + 4), and the array SHALL be written to the output file for that screen index (for example `nametable_0.s`).
2. THE Nametable_Builder SHALL keep all tile IDs in a nametable within the CHR range (0-255).
3. IF a tilemap cell resolves to a tile ID outside the CHR range (0-255), THEN THE Nametable_Builder SHALL write an error message containing the invalid tile ID and its tile coordinates (column, row, screen index) to standard error, abort the conversion, and produce no output buffer.
4. IF the region of a `screens` entry for any of its N screens (32 columns x 30 rows, or the HUD source region of 32 columns x 4 rows) lies outside the bounds of the referenced tilemap, THEN THE Nametable_Builder SHALL write an error message containing the screen index, the tilemap number and the tilemap bounds to standard error, abort the conversion, and produce no output buffer.
5. THE Nametable_Builder SHALL read the HUD area (rows 0-3, all 128 tiles of columns 0-31) from the HUD source of the `screens` entry and the BG area (rows 4-29, all 832 tiles of columns 0-31) from the tilemap region of the screen, and SHALL write each into the offset positions of the output nametable array that correspond to its area.
6. WHEN the Nametable_Builder converts a Pyxel tilemap cell into a NES nametable entry, THE Nametable_Builder SHALL look up the "Pyxel tile coordinate -> CHR tile ID" table generated by the CHR_Encoder and convert the cell's Pyxel tile coordinate (u, v) into the corresponding CHR tile ID.
7. IF the CHR tile ID corresponding to the Pyxel tile coordinate (u, v) referenced by a tilemap cell does not exist in the conversion table, THEN THE Nametable_Builder SHALL write an error message containing the tilemap position (column, row, screen index) and the referenced Pyxel tile coordinate (u, v) to standard error, abort the conversion, and produce no output buffer.

---

### Requirement 4: Attribute Table Construction

**User Story:** As a Pyxel developer, I want the BG palette assignment of tiles converted into NES attribute tables, so that the per-16x16-block palette selection reaches the PPU correctly.

#### Acceptance Criteria

1. WHEN the `palette_map` of a screen (a 32x30 array of integers 0-3, built as defined in Requirement 13) is provided, THE Attribute_Builder SHALL generate an attribute table of 8x8 entries (64 bytes).
2. THE Attribute_Builder SHALL store four 2-bit palette numbers (0-3) in each attribute byte with this bit assignment, following the NES PPU specification: bits 1:0 = top-left 16x16 block, bits 3:2 = top-right 16x16 block, bits 5:4 = bottom-left 16x16 block, bits 7:6 = bottom-right 16x16 block.
3. THE Attribute_Builder SHALL assign the same palette number to all 8x8 tiles inside the same 16x16 block (following the fixed Manifest setting).
4. IF an attribute conflict is detected, meaning two or more different palette numbers are assigned inside the same 16x16 block, THEN THE Attribute_Builder SHALL write an error message containing the coordinates of the conflicting 16x16 block (column 0-15, row 0-14 in block units) and the palette numbers involved to standard error and abort the conversion.
5. THE Attribute_Builder SHALL keep the property that every attribute entry has a value in the range 0-3 (attribute table consistency property).
6. IF an input palette number is outside the range 0-3, THEN THE Attribute_Builder SHALL write an error message containing the out-of-range value and its position to standard error and abort the conversion.

---

### Requirement 5: Metasprite Construction

**User Story:** As a Pyxel developer, I want sprite definitions converted into NES 8x16 metasprites, so that several hardware sprites can be handled as one game object.

#### Acceptance Criteria

1. WHEN `SpriteDef` entries are provided, THE Metasprite_Builder SHALL generate a metasprite table in which each sprite is defined as a collection of one or more NES 8x16 hardware sprites, using the cell decomposition defined in Requirement 12.
2. WHEN the Metasprite_Builder generates a horizontally flipped variant of a sprite, THE Metasprite_Builder SHALL verify that the pixel array of the original sprite's tiles mirrored horizontally and the pixel array of the flipped reference (with the horizontal flip flag set) have the same color index value at every pixel coordinate (flip symmetry property).
3. THE Metasprite_Builder SHALL exclude from the metasprite definition any 8x16 hardware sprite whose upper and lower tiles both have all in-palette indices equal to 0 (empty sprite skip). THE Metasprite_Builder SHALL NOT exclude a hardware sprite when only one of its two tiles has all pixels equal to 0.
4. IF the number of hardware sprites in one row of a metasprite (horizontal direction) exceeds 8, THEN THE Metasprite_Builder SHALL write a warning message containing the metasprite name and the sprite count to standard error and continue the conversion (this can violate the 8-sprites-per-scanline hardware limit).
5. WHEN the Metasprite_Builder generates the horizontally flipped variant of a metasprite, THE Metasprite_Builder SHALL set the x offset of each hardware sprite to (metasprite_width - 8 - x), where x is the x offset of the same hardware sprite in the normal variant and metasprite_width is the `w` of the `SpriteDef` in pixels, and SHALL toggle bit 6 (horizontal flip) of the OAM attribute byte of that hardware sprite. The y offset and the tile number SHALL stay unchanged.
6. FOR ALL generated normal/flipped metasprite pairs, applying the flip transformation of criterion 5 to the flipped variant SHALL reproduce the normal variant (flip involution property, verified by a Hypothesis property-based test).

---

### Requirement 6: Deterministic Conversion

**User Story:** As a Pyxel developer, I want the same input to always give the same output, so that builds are reproducible and version control is easy.

#### Acceptance Criteria

1. IF the same byte sequences of `.pyxres` files and the same Manifest are given as input, THEN THE Converter SHALL generate output files with identical byte sequences, regardless of OS, Python version, execution order and number of runs. The compared output set SHALL explicitly include `chr.bin`, `assets.h` and every `nametable_N.s`.
2. THE Converter SHALL determine the tile ID assignment order from the listing order of `.pyxres` files in the Manifest (the priority order when there are several `.pyxres` files) and, within each `.pyxres` file, from the row-major scan order of the image (left to right, top to bottom). THE Converter SHALL NOT include non-deterministic elements such as randomness, lexicographic optimization or timestamps in its output.
3. WHEN the conversion completes successfully, THE Converter SHALL log the byte length and the CRC-32 checksum, in hexadecimal, of every generated asset (CHR, nametables, attribute tables, palettes, metasprites).

---

### Requirement 7: Error Handling and Validation

**User Story:** As a Pyxel developer, I want an immediate and clear error when my input violates the 8-bit subset constraints, so that debugging time is minimized.

#### Acceptance Criteria

1. IF a `.pyxres` file does not exist or cannot be read, THEN THE Converter SHALL write an error message containing the file path to standard error and abort the conversion (the detailed loader failure cases are defined in Requirement 11).
2. IF the Manifest does not exist or does not contain the `nes_colors` table, THEN THE Converter SHALL write an error message containing the name of the missing field to standard error and abort the conversion.
3. WHEN the game BG tile count of the background pattern table exceeds 161 slots, THE Converter SHALL write an error message containing the table kind (BG), the actual tile count and the limit (161 slots) to standard error and abort the conversion.
4. WHEN the tile count of the sprite pattern table exceeds 256 tiles, THE Converter SHALL write an error message containing the table kind (sprite), the actual tile count and the limit (256 tiles) to standard error and abort the conversion.
5. WHEN the color count of one palette exceeds 4, THE Converter SHALL write an error message containing the offending palette number and the actual color count to standard error and abort the conversion.
6. WHEN a nametable contains a tile ID outside the CHR range (above 255), THE Converter SHALL write an error message containing that tile ID and its position (row, column, screen index) to standard error and abort the conversion.
7. WHEN an attribute conflict is detected, meaning two or more different palette numbers are assigned inside the same 16x16 block, THE Converter SHALL write an error message containing the coordinates of the conflicting 16x16 block and the palette numbers involved to standard error and abort the conversion.
8. IF the conversion does not complete successfully, THEN THE Converter SHALL remove only its temporary output directory and SHALL leave the output directory (`out_dir`) untouched, so that no partial files are left and no file of a previous successful run is destroyed.
9. WHEN a validation error occurs, THE Converter SHALL report the first detected error and stop immediately, without running later validations (fail-fast).
10. IF the conversion ends with an error, THEN THE Converter SHALL return a non-zero exit code.

---

### Requirement 8: Pyxel Font Mapping

**User Story:** As a Pyxel developer, I want the Pyxel built-in font placed at the ASCII code positions of the NES CHR, so that NES games can write strings directly into the nametable.

#### Acceptance Criteria

1. THE Font_Mapper SHALL store each glyph of the Pyxel built-in font (95 characters, ASCII 0x20-0x7E) as 16 bytes of 2bpp CHR data in the CHR slot whose number equals the ASCII code. A Pyxel font glyph is 4x6 pixels. THE Font_Mapper SHALL place it in the top-left of the 8x8 tile (columns 0-3, rows 0-5) and fill the remaining area (columns 4-7 of all rows, and rows 6-7 of columns 0-3) with color index 0.
2. THE Font_Mapper SHALL use color index 3 for glyph stroke pixels and color index 0 (the common background color) for glyph background pixels, and SHALL place the font tiles in the background pattern table.
3. WHEN the font has been stored in CHR, THE Font_Mapper SHALL make the result verifiable at byte level: the nametable byte value corresponds one-to-one to the CHR slot number, and the 16 CHR bytes of each slot represent the correct glyph.
4. WHEN glyph data is encoded and then decoded, THE Font_Mapper SHALL produce a result that matches the original glyph color index array bit for bit (font glyph round-trip).
5. THE Font_Mapper SHALL read the glyph data from font data bundled in the Chronomicon repository, and THE Converter SHALL NOT require the Pyxel package at run time to obtain the font.
6. THE Chronomicon repository SHALL include a third-party notices file named `THIRD_PARTY_NOTICES.md` that states the origin (project and source) of the bundled Pyxel built-in font data and contains the full text of the MIT license that applies to it.

---

### Requirement 9: Output Format

**User Story:** As a Pyxel developer, I want the conversion result in a format that the cc65 build system can read directly, so that I can build the NES ROM without converting assets by hand.

#### Acceptance Criteria

1. WHEN the conversion completes successfully, THE Converter SHALL output a fixed-length 8192-byte `chr.bin` file that concatenates the background pattern table ($0000-$0FFF) and the sprite pattern table ($1000-$1FFF), with unused areas filled with zero.
2. WHEN the conversion completes successfully, THE Converter SHALL output a cc65 C header file `assets.h` that contains the palette arrays as `const unsigned char[]` and the metasprite definitions, for both the normal and the horizontally flipped variant, in `oam_meta_spr` format: repeated groups of four bytes (x_offset, y_offset, tile, attr), terminated by the byte 128. THE Converter SHALL write x_offset and y_offset as signed bytes.
3. WHEN the conversion completes successfully, THE Converter SHALL output, for each screen index N (starting at 0), a file `nametable_N.s` that describes the nametable (960 bytes), the attribute table (64 bytes) and the objects table of the screen in ca65 assembly data format. The objects table lists the Manifest `objects` items that target the screen (initial sprite placements, as defined in Requirement 14), and contains only the terminator byte $ff when no item targets the screen.
4. THE Converter SHALL keep the invariant that the size of `chr.bin` is always 8192 bytes.
5. THE Emitter SHALL first write all output files into a temporary directory, and only after the conversion has completed successfully SHALL move them into the output directory. IF the output directory does not exist, THEN THE Emitter SHALL create it before moving the files.
6. THE Converter SHALL write the common background color into byte 0 of every BG palette and every sprite palette in `assets.h`, that is offsets 0, 4, 8 and 12 of both `palette_bg` and `palette_sprite`, including padded palettes. Because sprite color 0 is transparent, this affects only the backdrop color.
7. WHEN `palette_bg` and then `palette_sprite` are uploaded as 32 consecutive bytes starting at $3F00 (subject to the Palette mirror), THE Converter SHALL emit arrays for which the backdrop color read back from $3F00 equals the common background color (palette mirror invariant). The CRC-32 log of palettes (Requirement 6.3) SHALL use these emitted bytes.

---

### Requirement 10: Conversion Fidelity Property

**User Story:** As a Pyxel developer, I want to verify that the converted assets are visually equivalent to the original Pyxel images, so that conversion mistakes that degrade the appearance are detected automatically.

#### Acceptance Criteria

1. WHEN any valid Pyxel scene (a combination of tiles, sprites and tilemaps satisfying the 8-bit subset constraints) is converted, THE Converter SHALL produce output for which sequence (a) equals sequence (b) at every pixel coordinate. Sequence (a) is the original Pyxel image converted pixel by pixel to NES color bytes through `nes_colors`. Sequence (b) is the NES-style re-render of the converted output (CHR data, palettes, nametable and attribute table, plus the metasprites for sprites). Both sequences consist of NES color bytes (conversion fidelity property).
2. THE Converter SHALL implement the conversion fidelity property as a Hypothesis property-based test (PBT) that is checked automatically on randomly generated valid Pyxel scene samples.
3. WHEN a CHR encode/decode round-trip is executed for any valid tile data, THE CHR_Encoder SHALL produce a decoded result that matches the original color index array bit for bit (CHR round-trip PBT).
4. THE reference renderer used by the tests SHALL model palette RAM with the Palette mirror (a write to $3F10, $3F14, $3F18 or $3F1C lands in $3F00, $3F04, $3F08 or $3F0C respectively), and the conversion fidelity property SHALL obtain its BG and sprite palettes by uploading the emitted `palette_bg` and `palette_sprite` arrays through that model.

---

### Requirement 11: Pyxres Loading

**User Story:** As a Pyxel developer, I want the converter to read my `.pyxres` file directly, so that I can convert a game without installing or running the Pyxel engine.

#### Acceptance Criteria

1. WHEN a path to a `.pyxres` file is provided, THE Pyxres_Loader SHALL open the file as a zip archive, parse its TOML content, and return the image banks (pixel arrays of Pyxel color indices 0-15) and the tilemaps (cells as image-bank tile coordinates), without importing or running the Pyxel engine.
2. THE Pyxres_Loader SHALL return the image banks and tilemaps in the order in which they are numbered in the `.pyxres` file.
3. IF the `.pyxres` file does not exist or cannot be read, THEN THE Pyxres_Loader SHALL write an error message containing the file path to standard error and stop the conversion.
4. IF the `.pyxres` file is not a valid zip archive, THEN THE Pyxres_Loader SHALL write an error message containing the file path to standard error and stop the conversion.
5. IF the TOML content of the `.pyxres` file is malformed, THEN THE Pyxres_Loader SHALL write an error message containing the file path and the TOML entry name to standard error and stop the conversion.
6. IF an expected entry (image bank or tilemap data) is missing from the `.pyxres` file, THEN THE Pyxres_Loader SHALL write an error message containing the file path and the name of the missing entry to standard error and stop the conversion.
7. IF a pixel value of an image bank is outside 0-15, THEN THE Pyxres_Loader SHALL write an error message containing the file path, the image bank number, the pixel position and the value to standard error and stop the conversion.
8. FOR ALL valid image banks and tilemaps generated by a Hypothesis strategy, writing them into a `.pyxres` archive and loading that archive with the Pyxres_Loader SHALL return image banks and tilemaps equal to the generated ones (loader round-trip property).

---

### Requirement 12: Manifest Sprite Definitions

**User Story:** As a Pyxel developer, I want to declare my sprites in the Manifest, so that the converter knows which image-bank rectangles become metasprites and which palette each one uses.

#### Acceptance Criteria

1. THE Manifest SHALL contain a `sprites` list in which each entry is a `SpriteDef` with the fields `name`, `image_bank`, `u`, `v`, `w`, `h` and `palette`.
2. IF the `w` of a `SpriteDef` is not a multiple of 8, THEN THE Converter SHALL write an error message containing the sprite name and the offending `w` value to standard error and abort the conversion.
3. IF the `h` of a `SpriteDef` is not a multiple of 16, THEN THE Converter SHALL write an error message containing the sprite name and the offending `h` value to standard error and abort the conversion.
4. IF the `palette` of a `SpriteDef` does not reference a defined sprite palette, THEN THE Converter SHALL write an error message containing the sprite name and the undefined palette name to standard error and abort the conversion.
5. WHEN a `SpriteDef` of size w x h is converted, THE Metasprite_Builder SHALL decompose it into (w/8) x (h/16) cells of 8x16 hardware sprites, in row-major order (left to right, top to bottom).
6. IF the rectangle of a `SpriteDef` (`u`, `v`, `w`, `h`) lies outside the bounds of its image bank, THEN THE Converter SHALL write an error message containing the sprite name, the image bank number and the bank size to standard error and abort the conversion.

---

### Requirement 13: BG Palette Regions and palette_map

**User Story:** As a Pyxel developer, I want to assign BG palettes to rectangles of the image bank, so that every tile gets a fixed palette and the attribute table can be built without guessing.

#### Acceptance Criteria

1. THE Manifest SHALL contain a `bg_palette_regions` list in which each entry has the fields `image_bank`, `u`, `v`, `w`, `h` and the name of a BG palette.
2. THE Converter SHALL determine the BG palette of an image tile as the palette of the region that contains the top-left pixel position of that tile.
3. WHEN the Converter builds the `palette_map` of a screen, THE Converter SHALL set each cell of the map to the number of the BG palette of the image tile referenced by the corresponding tilemap cell, producing a 32x30 `palette_map` per screen.
4. IF the top-left pixel position of a tile referenced by a tilemap cell falls in no `bg_palette_regions` entry, THEN THE Converter SHALL write an error message containing the tile coordinates (image bank, u, v) to standard error and abort the conversion.
5. IF the top-left pixel position of a tile falls in two or more `bg_palette_regions` entries that assign different palettes, THEN THE Converter SHALL write an error message containing the tile coordinates and the conflicting palette names to standard error and abort the conversion.
6. IF a `bg_palette_regions` entry names a BG palette that is not defined in the Manifest, THEN THE Converter SHALL write an error message containing the region and the undefined palette name to standard error and abort the conversion.
7. THE Converter SHALL pass the `palette_map` of each screen to the Attribute_Builder.
8. FOR ALL valid tilemap regions and `bg_palette_regions` that Hypothesis generates with no overlapping regions, every cell of the generated `palette_map` SHALL equal the palette number of the region that contains the top-left pixel position of the tile referenced by that cell (palette_map consistency property).

---

### Requirement 14: Screen Definitions

**User Story:** As a Pyxel developer, I want to declare which tilemap regions form my screens and where the HUD comes from, so that the converter builds one nametable per screen from the right data.

#### Acceptance Criteria

1. THE Manifest SHALL contain a `screens` list in which each entry has the required fields `tilemap` (tilemap number), `x` and `y` (start position in tiles), `count` (screen count N, an integer of at least 1) and a HUD source (`hud_tilemap`, `hud_x`, `hud_y`), and MAY contain the optional field `objects`, a list of initial object placements in which each item has `name` (the name of a SpriteDef), `x` and `y` (display position in pixels) and an optional `screen` (0-based screen index inside the entry, default 0).
2. THE Converter SHALL treat the HUD source as a region of 4 rows x 32 columns of the tilemap `hud_tilemap`, starting at tile position (`hud_x`, `hud_y`).
3. IF a `screens` entry omits a required field or has a `count` below 1, THEN THE Converter SHALL write an error message containing the screen entry position in the list and the name of the offending field to standard error and abort the conversion.
4. IF a `screens` entry references a tilemap number that the Pyxres_Loader did not return, THEN THE Converter SHALL write an error message containing the screen entry position and the tilemap number to standard error and abort the conversion.
5. WHEN the Converter processes screens, THE Converter SHALL number the screens consecutively from 0, in the order of the `screens` entries and, within an entry, from left to right.
6. IF an `objects` item names a sprite that is not in the Manifest `sprites` list, THEN THE Converter SHALL write an error message containing the screen entry position, the item position in the `objects` list and the unknown name to standard error and abort the conversion.
7. IF an `objects` item has an `x` or `y` value outside 0-255, THEN THE Converter SHALL write an error message containing the screen entry position, the item position, the field name and the offending value to standard error and abort the conversion.
8. IF an `objects` item has a `screen` value outside 0 to `count` - 1 of its entry, THEN THE Converter SHALL write an error message containing the screen entry position, the item position, the `screen` value and the `count` of the entry to standard error and abort the conversion.
9. WHEN a screen has no `objects` items (the `objects` list is absent or empty, or no item targets that screen), THE Emitter SHALL write an objects table in the `nametable_N.s` file of that screen that contains only the terminator byte $ff.
10. WHEN a screen has `objects` items, THE Emitter SHALL write an objects table in the `nametable_N.s` file of that screen that lists the items targeting that screen in Manifest order, each as the three bytes x, y and metasprite index (the position of the SpriteDef in the Manifest `sprites` list), followed by the terminator byte $ff.
11. THE Emitter SHALL write the y value of each objects table item as the display Y (the screen row of the top of the object), so that the runtime subtracts 1 from the display Y when writing the OAM Y byte.
