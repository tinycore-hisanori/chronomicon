# Requirements Document

## Introduction

The rom-builder feature turns the output of the asset converter plus a small C game into a playable `.nes` file (iNES, mapper 0 / NROM) that boots in an emulator and on a real 8-bit console flash cartridge. It consists of three parts: a build pipeline (`chrono build <manifest>`), a C runtime library in `runtime/` with a small Pyxel-like API, and a headless boot test.

The source of truth for this spec is `docs/ROM_BUILDER_seed.md`, extended by the decisions listed in the Decisions section. All numbers, addresses, register values, file names and behaviours below are taken from that seed or from those decisions.

**Dependencies**

- The asset-converter spec guarantees (its Requirement 9.6 and 9.7) that byte 0 of every BG palette and every sprite palette is the common backdrop color. The Runtime relies on this when it uploads the 32 palette bytes at `$3F00` (Requirement 3). This spec does not re-specify that converter change.
- The asset converter is the Python package `converter/`, run as `chrono convert <manifest>` or, for compatibility, `.venv\Scripts\python -m converter <manifest> -o <dir>`. It outputs `chr.bin` (8192 bytes), `assets.h` (`palette_bg[16]`, `palette_sprite[16]`, and `metasprite_<name>` / `metasprite_<name>_flip` in oam_meta_spr format: x, y, tile, attr groups terminated by 128) and `nametable_N.s` (ca65 source with `_screenN_nametable` of 960 bytes, `_screenN_attr` of 64 bytes, and `_screenN_objects` as x, y, metasprite index entries terminated by `$ff`, where y is the display Y).
- The toolchain rules are recorded in `steering/tech.md`: cc65 2.19 on PATH, Node 20+ (v24 installed), toolchains are never installed automatically, and any new dependency requires asking the user first.
- The reference renderer is `tests/reference_renderer.py`, which provides `render_nes_frame` and `upload_palette`.
- The emulator is **tinynes**, the user's existing emulator (MIT license, Tiny Core), provided as `web/nes.js` and added to the repository by the user. It runs under Node and exports `module.exports = NES`. Its API is: `new NES()`, `load(Uint8Array)`, `frame()` (runs one frame), `indexBuffer` (Uint8Array of 256*240 NES color indices), `frameBuffer`, `ram` (Uint8Array of 0x800 bytes, CPU RAM) and `setButton(0, NES.BTN.*, bool)`. This spec does not change tinynes.

**In scope (v1)**

- Build pipeline `chrono build <manifest>` and the `chrono convert <manifest>` subcommand.
- C runtime library `runtime/` with the API listed in Requirement 5 to Requirement 9.
- Password (save code) functions in the Runtime (Requirement 12).
- Headless boot test that runs the ROM in tinynes (`web/nes.js`, under Node) and compares the first screen with the reference renderer.

**Out of scope (v1)**

- Writing or modifying an emulator. tinynes is provided by the user.
- Scrolling. Screens are flip-screen rooms: walking off an edge loads the next screen with rendering off for at most 2 frames. This avoids the sprite-0 HUD split.
- Music. Only sound effects are supported (pulse and noise register writes from C).
- Mappers other than NROM.
- Python game logic translation. The game logic is written in C against the runtime API.

## Glossary

- **Builder**: The `chrono build <manifest>` subcommand of the `chrono` CLI that runs the asset converter, compiles and links the Runtime and game, and writes the `.nes` file. The `chrono` CLI has the subcommands `chrono convert <manifest>` (the existing converter behaviour and options) and `chrono build <manifest>`.
- **Converter**: The Python package `converter/` that produces `chr.bin`, `assets.h` and `nametable_N.s` from a Manifest. It is run by `chrono convert <manifest>` and by `python -m converter`.
- **Manifest**: The input description file of a game. The Builder reads the fields `name` (required; the base name of the output ROM), `game_sources` (list of game C/asm source files), `prg_kb` (PRG size in KB, 16 or 32) and `mirroring` (vertical or horizontal).
- **Runtime**: The C and assembly library in `runtime/` (`runtime/*.c`, `runtime/*.s`, `runtime/chrono.h`, `runtime/nrom.cfg`) that provides startup, NMI handling and the game-facing API.
- **Linker_Config**: The file `runtime/nrom.cfg` that defines the NROM memory map for ld65.
- **iNES_Header**: The 16-byte header at the start of a `.nes` file.
- **NMI_Handler**: The Runtime routine that runs once per frame at vertical blank.
- **OAM_Shadow**: The 256-byte copy of sprite memory at `$0200-$02FF` that the NMI_Handler transfers to the PPU by DMA.
- **VRAM_Update_Queue**: The Runtime buffer of pending PPU memory writes that the NMI_Handler applies during vertical blank.
- **VRAM_Ready_Flag**: The Runtime flag that `wait_frame()` sets to mark the VRAM_Update_Queue as completely built. The NMI_Handler applies the VRAM_Update_Queue only while the flag is set and clears the flag after applying.
- **Flip_Screen_Room**: One full-screen room. Moving off an edge loads the next room with rendering off for at most 2 frames.
- **Metasprite**: A group of hardware sprites in oam_meta_spr format, as emitted in `assets.h`.
- **Pad_State**: The held-button and pressed-this-frame bitmasks of controller 1, computed once per frame by `pad_update`.
- **Reference_Renderer**: The test module `tests/reference_renderer.py` (`render_nes_frame`, `upload_palette`) that renders a screen from converter output.
- **tinynes**: The user's emulator in `web/nes.js` (MIT license, Tiny Core). API: `new NES()`, `load(Uint8Array)`, `frame()`, `indexBuffer` (256*240 NES color indices), `frameBuffer`, `ram` (0x800 bytes of CPU RAM), `setButton(0, NES.BTN.*, bool)`, `module.exports = NES`.
- **Boot_Test**: The automated test that builds the Sample_Game, runs the ROM under Node in tinynes and compares the result with the Reference_Renderer.
- **Sample_Game**: The small C game used by the Boot_Test, located in `samples/boot_test/`, which holds `main.c` and the Manifest. The Boot_Test generates the `.pyxres` file. The game shows the `player` Metasprite at (64, 120), and pressing Start adds 16 to its x.
- **PPU**: The picture processing unit of the 8-bit console, accessed through registers `$2000-$2007`.
- **password_encode**: The Runtime function `void password_encode(const unsigned char *state, unsigned char len, char *out)` that turns `len` state bytes into a NUL-terminated password string.
- **password_decode**: The Runtime function `unsigned char password_decode(const char *in, unsigned char len, unsigned char *state)` that checks a password string and, on success, restores `len` state bytes.
- **PASSWORD_MAX_STATE_LEN**: The constant in `chrono.h` that gives the largest `len` accepted by `password_encode` and `password_decode`.

## Requirements

### Requirement 1: Build pipeline

**User Story:** As a game developer, I want one command that turns my Manifest and C sources into a ROM, so that I can run my game without invoking each tool by hand.

#### Acceptance Criteria

1. WHEN `chrono build <manifest>` is run, THE Builder SHALL run the Converter into `build/assets/`, then compile `runtime/*.c`, `runtime/*.s`, the game sources listed in the Manifest field `game_sources` and `build/assets/nametable_*.s`, and link them with `runtime/nrom.cfg`.
2. THE Builder SHALL write an iNES_Header consisting of the bytes `NES\x1A`, a PRG bank count of 2 when the Manifest field `prg_kb` is 32 or 1 when it is 16, a CHR bank count of 1, byte 6 bit 0 set to 1 when the Manifest field `mirroring` is vertical and 0 when it is horizontal, mapper number 0, and bytes 7 to 15 equal to zero.
3. THE Builder SHALL append `chr.bin`, which is exactly 8192 bytes, after the PRG data.
4. IF the linked PRG data exceeds the PRG size selected by `prg_kb`, THEN THE Builder SHALL stop with a non-zero exit code, write no `.nes` file, and print an error message that contains the name of the overflowing segment and the overflow in bytes, both parsed from the ld65 map file.
5. WHEN the build succeeds, THE Builder SHALL exit with code 0 and print the ROM size in bytes and the CRC-32 of the ROM as 8 hexadecimal digits.
6. WHEN the Builder is run twice with identical inputs, THE Builder SHALL produce byte-identical `.nes` files.
7. IF `cc65`, `ca65` or `ld65` cannot be found on PATH, THEN THE Builder SHALL stop with a non-zero exit code and an error message that contains the name of the missing tool, and SHALL NOT download or install any tool.
8. WHEN the build succeeds, THE Builder SHALL write the ROM to `build/<name>.nes`, where `<name>` is the value of the Manifest field `name`.
9. IF the Manifest has no `name` field, or the value of `name` is not usable as a file name, THEN THE Builder SHALL stop with a non-zero exit code and print an error message that names the field `name`.
10. WHEN `chrono convert <manifest>` is run, THE `chrono` CLI SHALL run the Converter with the behaviour and options of the existing converter command.
11. WHEN `chrono build <manifest>` is run, THE `chrono` CLI SHALL run the Builder as described in criteria 1 to 9.
12. WHEN `python -m converter <manifest>` is run, THE Converter SHALL behave unchanged from its behaviour before the `chrono` subcommands were introduced.

### Requirement 2: Memory map

**User Story:** As a runtime developer, I want a fixed NROM memory map, so that code, vectors, OAM shadow and RAM never overlap.

#### Acceptance Criteria

1. WHERE `prg_kb` is 32, THE Linker_Config (`runtime/nrom.cfg`) SHALL place PRG at `$8000`, so that the ld65 map file reports the PRG segments starting at `$8000`.
2. WHERE `prg_kb` is 16, THE Linker_Config (`runtime/nrom.cfg`) SHALL place PRG at `$C000`, so that the ld65 map file reports the PRG segments starting at `$C000`.
3. THE Linker_Config SHALL place the vectors (NMI, RESET, IRQ) at `$FFFA`, so that the last 6 bytes of the PRG data in the output ROM, ending at CPU address `$FFFF`, hold the NMI, RESET and IRQ vectors in that order.
4. THE Linker_Config SHALL reserve zero page `$00-$FF`, so that every zero-page segment in the ld65 map file lies within `$00-$FF`.
5. THE Linker_Config SHALL place the OAM_Shadow at `$0200-$02FF`, page aligned, so that the ld65 map file reports the OAM_Shadow start address as `$0200` and its size as no more than 256 bytes.
6. THE Linker_Config SHALL place the C stack and BSS in `$0300-$07FF`, so that every BSS segment and the C stack in the ld65 map file lie within `$0300-$07FF`.
7. THE Linker_Config SHALL keep the vectors, zero page, OAM_Shadow, and C stack and BSS ranges non-overlapping, so that no two segments in the ld65 map file share an address.

### Requirement 3: Reset and PPU initialization

**User Story:** As a runtime developer, I want a deterministic power-on sequence, so that the game starts from a known hardware state on emulators and real consoles.

#### Acceptance Criteria

1. WHEN the RESET vector runs, THE Runtime SHALL execute the following in this order: `sei`, `cld`, write `$40` to `$4017` (APU frame IRQ disabled), write `0` to `$4010` (DMC IRQ disabled), set the stack pointer to `$FF`, write `0` to `$2000`, then write `0` to `$2001`.
2. WHEN step 1 of this sequence has completed, THE Runtime SHALL wait for two vertical blanks by polling bit 7 of `$2002`, where each wait ends when bit 7 reads 1.
3. WHEN the second vertical blank has been detected, THE Runtime SHALL write `$00` to every RAM byte in `$0000-$07FF` using code that contains no `JSR` and runs before any stack use, and after the clear THE Runtime SHALL run the cc65 routines `copydata` and `zerobss` and initialize the C stack pointer `sp`.
4. WHEN `copydata`, `zerobss` and the initialization of `sp` have completed, THE Runtime SHALL write `$FF` to the Y byte of all 64 OAM_Shadow entries (the shadow at `$0200-$02FF`), which hides all sprites.
5. WHEN OAM_Shadow has been initialized, THE Runtime SHALL write 32 palette bytes to `$3F00`, taking the `palette_bg` array from `assets.h` first and the `palette_sprite` array from `assets.h` second.
6. WHEN the palette upload has completed, THE Runtime SHALL write 1024 bytes to `$2000`, taking the screen 0 data from `_screen0_nametable` first and `_screen0_attr` second.
7. WHEN the screen 0 upload has completed, THE Runtime SHALL, before enabling rendering, read `$2002` (which resets the PPU address latch) and write `0` to `$2005` twice so that the scroll is 0, then write PPUCTRL (`$2000`) with bit 7 = 1 (NMI on), bit 5 = 1 (8x16 sprites), bit 4 = 0 (BG pattern table at `$0000`) and VRAM address increment 1, and then write PPUMASK (`$2001`) to show background and sprites, including the left 8 pixels.

### Requirement 4: NMI handler

**User Story:** As a runtime developer, I want a short, fixed per-frame NMI routine, so that video updates are glitch-free and game logic never runs at vertical blank.

#### Acceptance Criteria

1. WHEN an NMI occurs, THE NMI_Handler SHALL first write `0` to `$2003` and then write `$02` to `$4014`, transferring the 256-byte OAM_Shadow at `$0200-$02FF` to OAM by DMA.
2. WHEN the OAM DMA has completed and the VRAM_Ready_Flag is set, THE NMI_Handler SHALL apply the VRAM_Update_Queue, writing at most 64 payload bytes to `$2007` during that NMI, where the 3-byte entry headers are not counted (decided by the user).
3. IF the VRAM_Update_Queue holds more than 64 bytes during an NMI, THEN THE NMI_Handler SHALL leave the bytes beyond the 64th in the queue, in their original order, for application in a later NMI in which the VRAM_Ready_Flag is set (decided by the user).
4. WHEN the VRAM_Update_Queue has been applied, THE NMI_Handler SHALL write the scroll registers as its last PPU writes, by writing `0` to `$2005` twice and then writing the nametable bits of PPUCTRL.
5. WHEN the scroll registers have been written, THE NMI_Handler SHALL set the frame flag that `wait_frame()` waits for.
6. THE NMI_Handler SHALL execute no game logic.
7. WHEN an NMI occurs, THE NMI_Handler SHALL save the A, X and Y registers on entry and restore them before returning from the interrupt.
8. WHEN the NMI_Handler has applied the VRAM_Update_Queue, THE NMI_Handler SHALL clear the VRAM_Ready_Flag.
9. WHILE the VRAM_Ready_Flag is clear, THE NMI_Handler SHALL write no VRAM_Update_Queue byte to the PPU.

### Requirement 5: Frame synchronization and controller input

**User Story:** As a game developer, I want simple frame-wait and button functions, so that I can write a game loop like a Pyxel game.

#### Acceptance Criteria

1. THE Runtime SHALL declare `void wait_frame(void);`, `void pad_update(void);`, `btn(b)` and `btnp(b)` in `runtime/chrono.h`.
2. WHEN `wait_frame()` is called, THE Runtime SHALL return only after the NMI_Handler has set the frame flag for a new frame, meaning a frame flag set by an NMI that occurred after the call began.
3. WHEN `pad_update()` is called, THE Runtime SHALL strobe `$4016` once and then perform exactly 8 reads of controller 1 from `$4016`.
4. THE Runtime SHALL map the 8 reads, in read order, to the buttons A, B, Select, Start, Up, Down, Left, Right (standard controller order), and SHALL define one button constant for each of these 8 buttons in `runtime/chrono.h` for use as the argument `b` of `btn(b)` and `btnp(b)`.
5. WHEN `pad_update()` completes, THE Runtime SHALL make `btn(b)` return true for each button held in the state just read, and false for every other button.
6. WHEN `pad_update()` completes, THE Runtime SHALL make `btnp(b)` return true for each button where `now & ~prev` is set, where `now` is the state just read and `prev` is the state read by the previous `pad_update()` call, and false for every other button.
7. THE Runtime SHALL compute `btnp(b)` edge detection only inside `pad_update()`, and SHALL NOT read `$4016` in `btn(b)`, `btnp(b)` or anywhere else in the same frame.
8. IF `btn(b)` or `btnp(b)` is called before the first `pad_update()` call, THEN THE Runtime SHALL return false for every button.

### Requirement 6: Sprite output

**User Story:** As a game developer, I want to place metasprites on screen, so that characters and objects appear at the intended positions.

#### Acceptance Criteria

1. WHEN `void meta_spr(unsigned char x, unsigned char y, const unsigned char *meta);` is called and the OAM_Shadow has enough free entries for every hardware sprite of the Metasprite, THE Runtime SHALL append those hardware sprites to the OAM_Shadow after the entries already used in the current frame, in the order they appear in the Metasprite data.
2. THE Runtime SHALL read Metasprite data in the assets.h `oam_meta_spr` format: groups of four bytes (x_offset, y_offset, tile, attr), with x_offset and y_offset as signed bytes, terminated by the byte 128.
3. WHEN `meta_spr(x, y, meta)` writes a hardware sprite, THE Runtime SHALL write the four OAM bytes in the order Y, tile, attr, X.
4. WHEN `meta_spr(x, y, meta)` writes a hardware sprite, THE Runtime SHALL write OAM X equal to `x + x_offset` and OAM Y equal to `y + y_offset - 1`, both computed modulo 256 (8-bit wrap).
5. WHEN `meta_spr(x, y, meta)` writes a hardware sprite, THE Runtime SHALL copy the tile and attr bytes from the Metasprite data into the OAM entry unchanged.
6. IF the OAM_Shadow already holds 64 hardware sprites, or the number of free OAM_Shadow entries is smaller than the number of hardware sprites in the Metasprite, THEN THE Runtime SHALL skip the `meta_spr` call, writing no hardware sprite of that Metasprite to the OAM_Shadow and leaving all existing entries unchanged.
7. WHEN `oam_clear()` is called at the start of a frame, THE Runtime SHALL set OAM Y to `$FF` for every OAM_Shadow entry not used in that frame and reset the append position to entry 0 (decided by the user).

### Requirement 7: Text and VRAM update queue

**User Story:** As a game developer, I want to print strings on the background, so that I can show a HUD and messages.

#### Acceptance Criteria

1. WHEN `void text(unsigned char col, unsigned char row, const char *s);` is called with a non-empty string, THE Runtime SHALL queue the string bytes directly in the VRAM_Update_Queue, using the ASCII code of each character as the tile index, with the first byte targeting nametable address `$2000 + row*32 + col`.
2. IF `text(col, row, s)` is called with an empty string, or with `col` >= 32, or with `row` >= 30, THEN THE Runtime SHALL queue no VRAM write (column and row rule decided by the user).
3. THE Runtime SHALL queue every VRAM write with a length from 1 to 32 bytes.
4. IF `text(col, row, s)` is called with a string longer than 32 characters, THEN THE Runtime SHALL split it into consecutive VRAM writes of 1 to 32 bytes each, where each write targets the nametable address immediately following the last byte of the previous write. IF the string would run past nametable address `$23BF`, THEN THE Runtime SHALL truncate it at `$23BF` so that no attribute byte is written. IF the whole string (with its entry headers) does not fit in the VRAM_Update_Queue, THEN THE Runtime SHALL drop the whole string and queue none of its bytes (decided by the user).
5. WHEN the NMI runs and the VRAM_Ready_Flag is set, THE Runtime SHALL apply at most 64 payload bytes of queued VRAM writes in that frame (entry headers not counted, decided by the user), keep queued writes that are not applied in the queue for a later NMI, and apply no write partially (decided by the user).
6. WHEN `wait_frame()` is called, THE Runtime SHALL set the VRAM_Ready_Flag, so that the NMI_Handler never applies a half-built VRAM_Update_Queue.

### Requirement 8: Screen loading

**User Story:** As a game developer, I want to switch between flip-screen rooms, so that my game can have more than one screen.

#### Acceptance Criteria

1. WHEN game code calls `void load_screen(unsigned char n);` with N in the range 0 to (number of built screens - 1), THE Runtime SHALL wait for vertical blank, write `0` to `$2001` (rendering off), and then write the 1024 bytes of nametable and attribute data for screen N to the nametable at `$2000` (nametable from `_screenN_nametable`, attribute table from `_screenN_attr`), and THE Runtime SHALL empty the VRAM_Update_Queue (decided by the user).
2. WHILE `load_screen` is writing the nametable and attribute table, THE Runtime SHALL keep rendering off and SHALL suspend the NMI_Handler's PPU processing, by either clearing PPUCTRL bit 7 or setting a flag that makes the NMI_Handler skip the OAM DMA, the VRAM_Update_Queue and the scroll writes, so that the large write to `$2006` and `$2007` does not occur during visible rendering and is not interrupted by NMI PPU writes.
3. THE Runtime SHALL use `load_screen` as the only operation that writes blocks larger than 32 bytes to `$2006` and `$2007`.
4. WHEN `load_screen` has finished writing, THE Runtime SHALL resume at the next vertical blank by turning the NMI PPU processing on again and re-enabling rendering with the scroll reset as in Requirement 3.7, SHALL keep rendering off for at most 2 frames between the previous displayed frame and the first frame of screen N, and SHALL NOT scroll.
5. THE Runtime SHALL leave the decision of when to call `load_screen` to game code, and SHALL NOT detect screen edges itself.
6. IF `load_screen` is called with N greater than or equal to the number of built screens, THEN THE Runtime SHALL return without changing rendering state or VRAM (decided by the user).

### Requirement 9: Sound effects

**User Story:** As a game developer, I want simple sound effects, so that my game has audio feedback.

#### Acceptance Criteria

1. THE Runtime SHALL declare `void sfx(unsigned char id);` in `runtime/chrono.h`.
2. WHEN `sfx(id)` is called with an `id` that has a defined effect, THE Runtime SHALL start that effect by writing registers of the pulse 1 (`$4000`-`$4003`), pulse 2 (`$4004`-`$4007`) or noise (`$400C`-`$400F`) channels from C.
3. WHEN `sfx(id)` is called, THE Runtime SHALL write only to registers in `$4000`-`$4007`, `$400C`-`$400F` and `$4015`, and SHALL leave the DMC registers (`$4010`-`$4013`) and `$4017` unchanged from their RESET values.
4. WHEN RESET initialisation runs, THE Runtime SHALL write `$4015` to enable the pulse 1, pulse 2 and noise channels (decided by the user).
5. IF `sfx(id)` is called with an `id` that has no defined effect, THEN THE Runtime SHALL return without writing any APU register (decided by the user).
6. THE Runtime SHALL provide sound effects only, with no music playback.
7. THE Runtime SHALL define in `chrono.h` the sound effect ids `SFX_JUMP` = 0 (pulse 1, rising sweep), `SFX_HIT` = 1 (noise, short burst), `SFX_SELECT` = 2 (pulse 2, short blip) and `SFX_ITEM` = 3 (pulse 2, two notes).

### Requirement 10: Known pitfalls as testable rules

**User Story:** As a maintainer, I want the known hardware and toolchain pitfalls expressed as checkable rules, so that earlier bugs are not repeated.

#### Acceptance Criteria

1. THE Runtime SHALL queue no VRAM write of length 0, so that no VRAM write routine of the Runtime receives a length of 0 (a zero-length `vram_write`-style write writes 64 KB). A unit test that calls `text` with an empty string (Requirement 7.2) SHALL find the VRAM_Update_Queue unchanged, and a static check of the Runtime sources SHALL find no VRAM write call that can receive length 0. The unit test SHALL run the Runtime in the Boot_Test emulator or in a test harness (the design will choose).
2. THE Runtime SHALL read controller 1 in exactly one place, `pad_update()` (Requirements 5.3 and 5.7), because polling the pad twice in one frame breaks `btnp`. A static check of the Runtime sources SHALL find no `$4016` read outside `pad_update()`, and a unit test SHALL call `pad_update()` once per frame and find `btnp(b)` true for a button in exactly one frame of a held press. The unit test SHALL run the Runtime in the Boot_Test emulator or in a test harness (the design will choose).
3. THE Runtime SHALL declare in C with `#pragma zpsym` every zero-page symbol that is also referenced from assembly. A static check SHALL find, for each symbol imported with `.importzp` or exported with `.exportzp` in `runtime/*.s`, a matching `#pragma zpsym` in the Runtime C sources.
4. THE Runtime SHALL write OAM Y equal to the display Y minus 1 for every hardware sprite (Requirement 6.4), because sprites appear one line below their OAM Y. A unit test SHALL call `meta_spr(x, y, meta)` with a Metasprite whose entries have Y offsets 0 and 8, and SHALL find the OAM_Shadow Y bytes equal to `y - 1` and `y + 7`. The unit test SHALL run the Runtime in the Boot_Test emulator or in a test harness (the design will choose).
5. THE Runtime SHALL write to `$2006` or `$2007` only in one of three places: the VRAM_Update_Queue application inside the NMI_Handler (Requirement 4.2), `load_screen` with rendering off (Requirements 8.1 to 8.3), and the RESET upload before rendering is enabled (Requirements 3.5 and 3.6). Outside vertical blank, such writes corrupt the screen. A static check of the Runtime sources SHALL find no other `$2006` or `$2007` write, and the Boot_Test (Requirement 11.2) SHALL find the frame 30 background identical to the Reference_Renderer output.
6. THE Runtime SHALL upload the 32 palette bytes at `$3F00` as `palette_bg[16]` followed by `palette_sprite[16]` (Requirement 3.5) and SHALL rely on byte 0 of every BG and sprite palette being the common backdrop color, as guaranteed by asset-converter Requirements 9.6 and 9.7, because `$3F10`, `$3F14`, `$3F18` and `$3F1C` mirror `$3F00`, `$3F04`, `$3F08` and `$3F0C`. A unit test SHALL pass the Sample_Game `palette_bg` and `palette_sprite` to `upload_palette` in that order and SHALL find the backdrop color at `$3F00` equal to byte 0 of `palette_bg`.
7. THE NMI_Handler and the VRAM queue apply routine (`vram_apply`) SHALL use none of cc65's shared zero-page locations (`ptr1` to `ptr4`, `tmp1` to `tmp4`, `sreg`, `regsave`, `c_sp` and `regbank`), and SHALL use only dedicated zero-page variables of the Runtime, because the NMI interrupts C code at any instruction and would corrupt those locations. A static check of `runtime/nmi.s` and of every routine the NMI calls SHALL find no reference to those symbols.

### Requirement 11: Boot test

**User Story:** As a maintainer, I want an automated end-to-end check of the ROM, so that I know the pipeline produces a ROM that boots and responds to input.

#### Acceptance Criteria

1. WHEN the Boot_Test runs, THE Boot_Test SHALL build the Sample_Game, load the resulting `.nes` file into tinynes (`web/nes.js`) under Node with `load(Uint8Array)`, and run 30 frames with `frame()` and no input.
2. WHEN 30 frames have run, THE Boot_Test SHALL compare the background of frame 30, with sprites excluded, against `render_nes_frame` of screen 0 from the Reference_Renderer.
3. THE Boot_Test SHALL require the compared background pixels to match pixel for pixel, with zero differing pixels over the full 256x240 frame.
4. WHEN the Boot_Test presses Start for one frame, THE Boot_Test SHALL read `ram[0x0203]` (the X byte of OAM entry 0 in the OAM_Shadow) and find 64 plus the x_offset of the first hardware sprite of the `player` Metasprite (0 for the Sample_Game) before Start is pressed, and 80 plus that x_offset (80 for the Sample_Game) after Start is pressed, which shows that controller input and OAM DMA work. The Boot_Test SHALL press and release Start with `setButton(0, NES.BTN.START, true)` and `setButton(0, NES.BTN.START, false)`.
5. THE Boot_Test SHALL read frame 30 from the tinynes `indexBuffer`, a 256x240 buffer of NES color indices, and SHALL compare it with the Reference_Renderer frame in the same format, without an RGB mapping.
6. THE Boot_Test SHALL exclude sprites from the comparison by masking, in both frames, every pixel covered by a sprite in the OAM_Shadow, read from `ram[0x0200..0x02FF]`, because tinynes has no background-only buffer. Each OAM entry covers 8 columns starting at its X byte and 16 rows starting one line below its Y byte, clipped to the frame.
7. THE Boot_Test SHALL take the reference palettes from the generated `assets.h` data that the ROM uploads through `upload_palette`, so that the Reference_Renderer and the ROM use the same palette values.
8. THE Boot_Test SHALL run from pytest and call Node as a subprocess.
9. IF Node is not found on PATH, THEN THE Boot_Test SHALL be reported as skipped with a message stating that Node is missing, and THE Boot_Test SHALL NOT install Node or any other dependency.
10. IF the background comparison fails, THEN THE Boot_Test SHALL fail and report the count of differing pixels and the coordinates of the first differing pixel.

### Requirement 12: Password (save code)

**User Story:** As a player of a converted game, I want to get a short password and type it back in later, so that I can resume my progress on a cartridge that has no battery-backed save memory, and a typing mistake is detected instead of loading wrong data.

#### Acceptance Criteria

1. THE Runtime SHALL declare in `chrono.h` the functions `void password_encode(const unsigned char *state, unsigned char len, char *out)` and `unsigned char password_decode(const char *in, unsigned char len, unsigned char *state)`. The decode signature and its return convention (1 = success, 0 = failure) are decided by the user. In both functions, `len` is the state length in bytes.
2. THE Runtime SHALL define in `chrono.h` the constant `PASSWORD_MAX_STATE_LEN`, the largest `len` that encode and decode accept, with the value 8. The longest password is therefore 14 characters (ceil(64 / 5) + 1), and the output buffer for `password_encode` needs 15 bytes including the NUL. `chrono.h` documents both values (decided by the user).
3. THE Runtime SHALL draw password characters only from the 32-symbol alphabet made of the uppercase letters A-Z without I and O (24 symbols) and the digits 2-9 (8 symbols). Each character carries 5 bits. The ASCII codes of all 32 symbols fall within 0x20-0x7E, so `text()` can display them. The alphabet is uppercase only, and `password_decode` rejects lowercase letters (decided by the user).
4. WHEN `password_encode` is called with 1 ≤ `len` ≤ `PASSWORD_MAX_STATE_LEN`, THE Runtime SHALL write to `out` exactly N = ceil(8 × `len` / 5) + 1 alphabet characters followed by one NUL byte, so the caller's buffer needs N + 1 bytes. The state bits are packed 5 per character in order, with unused trailing bits set to 0. The final character is a 5-bit checksum, as in criterion 5. The checksum occupying one whole 5-bit character and the NUL-terminated output are decided by the user. IF `password_encode` is called with `len` equal to 0 or greater than `PASSWORD_MAX_STATE_LEN`, THEN THE Runtime SHALL write an empty string (a single NUL byte) to `out` (decided by the user).
5. THE Runtime SHALL compute the checksum as the sum of all data symbols (their 5-bit values, including the symbol that holds padding bits) modulo 32, and SHALL store it as the last character of the password (decided by the user). Every single-character substitution of a valid password, whether in a data character or in the checksum character, by any other alphabet symbol is therefore always rejected by `password_decode`. This detection is deterministic, not probabilistic: substituting a data symbol changes the sum by a non-zero value modulo 32, so the stored checksum no longer matches, and changing the checksum character itself leaves the stored value different from the computed sum.
6. WHEN `password_decode` is called with a NUL-terminated `in` of exactly N characters (N as in criterion 4 for the given `len`), all from the alphabet, and the checksum matches, THE Runtime SHALL write the `len` decoded bytes to `state` and return 1. FOR the same `state` and `len`, decoding the output of `password_encode` SHALL reproduce the original bytes exactly.
7. IF `in` has a length other than N, or contains a character outside the alphabet (including lowercase letters, I, O, 0, 1 and spaces), or has a checksum mismatch, or `len` is 0 or greater than `PASSWORD_MAX_STATE_LEN`, THEN THE Runtime SHALL return 0 from `password_decode` and leave the buffer `state` unmodified. The length is checked with `strlen`, so `in` must be NUL-terminated (decided by the user).
8. THE Verification suite SHALL include Hypothesis property-based tests with two properties. First, for generated `state` bytes of generated `len` in 1..`PASSWORD_MAX_STATE_LEN`, encode followed by decode returns 1 and the original bytes. Second, for a generated valid password, a generated position, and a generated replacement alphabet symbol different from the original, decode returns 0. Both properties also run under the `dev` and `ci` profiles. Generated data stays small enough for the full suite to finish within 60 seconds under the `dev` profile.
9. THE Verification suite SHALL check the C implementation itself against the properties in criterion 8. Because cc65 targets only the 6502, the verification method is fixed (decided by the user). A Python reference implementation in `tests/` is the oracle. The C implementation is built with cc65 into a small test ROM and run in tinynes under Node. The test places inputs at RAM addresses resolved from the ld65 `-Ln` label file (fixed per ROM, with no reserved RAM range) (decided by the user), runs the ROM, reads the encode and decode results from RAM, and compares them with the Python oracle on generated cases, requiring identical encode output and identical decode results. No new tool is installed or used, and in particular no host C compiler such as gcc. A test that exercises only the Python reference does not satisfy this criterion.

## Decisions

1. `web/nes.js` is tinynes, provided by the user; writing an emulator is out of scope.
2. `<name>` in `build/<name>.nes` comes from the required Manifest field `name`.
3. The CLI uses the subcommands `chrono convert` and `chrono build`; `python -m converter` stays unchanged.
4. Sample_Game is `samples/boot_test/` (`main.c` and the Manifest); the Start press moves sprite 0 from x = 64 to x = 80, checked at `ram[0x0203]`.
5. Sound effect ids: 0 `SFX_JUMP`, 1 `SFX_HIT`, 2 `SFX_SELECT`, 3 `SFX_ITEM`.
6. Queue bytes beyond 64 in one NMI stay queued for a later NMI (4.3).
7. `oam_clear()` resets the append position to entry 0 (6.7).
8. Strings longer than 32 characters are split into several writes (7.4).
9. `load_screen(n)` with n out of range returns without changes (8.6).
10. `$4015` enables pulse 1, pulse 2 and noise at RESET (9.4), and an unknown sfx id is a silent no-op (9.5).
11. Password API and format (12.1 to 12.4, 12.7): `unsigned char password_decode(const char *in, unsigned char len, unsigned char *state)` returns 1 on success and 0 on failure. `PASSWORD_MAX_STATE_LEN` is 8, so the longest password is 14 characters and the output buffer needs 15 bytes including the NUL. The alphabet is uppercase only and decode rejects lowercase. Output length is ceil(8 * len / 5) + 1 characters, NUL-terminated, and decode checks length with `strlen`.
12. Checksum and bound (12.5): the checksum is the sum of all data symbols (5-bit values) modulo 32, stored as the last character. A single substitution changes the sum by a non-zero value modulo 32, so detection is deterministic.
13. C verification method (12.9): a Python reference implementation in `tests/` is the oracle. The C code is built with cc65 into a small test ROM and run in tinynes under Node. The test writes inputs to RAM addresses resolved from the ld65 `-Ln` label file, runs the ROM, reads the results from RAM and compares them with the oracle on generated cases. No new tools (no host C compiler such as gcc).
14. Test mailbox RAM addresses are resolved from the ld65 `-Ln` label file. They are fixed per ROM, and no RAM range is reserved for them (12.9).
15. The NMI budget of 64 bytes (4.2, 7.5) counts payload bytes written to `$2007` only. The 3-byte entry headers are not counted.
16. Accepted design additions: `text()` ignores `col` >= 32 or `row` >= 30 and truncates at `$23BF` (7.2, 7.4). `text()` drops a string that does not fit the queue whole (7.4). `load_screen` empties the VRAM queue (8.1). `password_encode` writes an empty string for an invalid `len` (12.4).
17. CLI change accepted: `chrono convert` and `chrono build` are the subcommands, the old `chrono <manifest>` form is gone, and `python -m converter` is unchanged (1.10 to 1.12).
18. tinynes `web/nes.js` carries "MIT License. Copyright (c) 2026 Tiny Core Inc." in its header, the same holder and year as the repository LICENSE.
