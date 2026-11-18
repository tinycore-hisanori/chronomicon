# Chronomicon — Spec seed: `rom-builder` (paste into Kiro as the starting point)

Goal: turn the asset-converter output plus a small C game into a playable `.nes` file (NROM, mapper 0) that boots in an emulator and on a real Famicom flash cartridge.

## 0. Fix first (asset-converter bug, small)

`$3F10/$3F14/$3F18/$3F1C` are hardware mirrors of `$3F00/$3F04/$3F08/$3F0C`. When the runtime uploads the 32 palette bytes in one go, byte 0 of each sprite palette overwrites the backdrop color.

- Emitter: write the common backdrop color into byte 0 of **every** BG and sprite palette (offsets 0, 4, 8, 12 of both arrays). Sprite color 0 is transparent anyway, so nothing visible changes except that the backdrop stays correct.
- Reference renderer: model the mirror (a write to `$3F10` lands in `$3F00`) and add a unit test that uploads both arrays in order and checks the backdrop.

## 1. Scope (v1)

In scope
- Build pipeline `chrono build <manifest>`: run the converter, compile the runtime and the game with cc65/ca65, link with ld65 for NROM, write the iNES header, output `build/<name>.nes`.
- A C runtime library `runtime/` with a small Pyxel-like API (below).
- A headless boot test that runs the ROM in the project's own emulator (`web/nes.js`, Node) and compares the first screen with the reference renderer.

Out of scope (v1)
- Scrolling. Screens are **flip-screen rooms**: walking off an edge loads the next screen with rendering off for one frame. This avoids the sprite-0 HUD split.
- Music. Sound effects only (pulse / noise register writes from C).
- Mappers other than NROM. Python game logic translation (the game logic is written in C against the runtime API).

## 2. Toolchain and environment (user installs this before Kiro starts)

- cc65 2.19 for Windows (`cc65`, `ca65`, `ld65` on PATH). Kiro must not download or install toolchains.
- Node 20+ for the boot test.
- `steering/tech.md`: add "cc65 2.19 on PATH; never install toolchains; ask before adding any dependency".

## 3. Requirements (EARS seeds)

R1 Build
1. WHEN `chrono build <manifest>` runs, THE Builder SHALL run the asset converter into `build/assets/`, then compile `runtime/*.c`, `runtime/*.s`, the game sources listed in the Manifest `game_sources`, and `build/assets/nametable_*.s`, and link them with `runtime/nrom.cfg`.
2. THE Builder SHALL write an iNES header: `NES\x1A`, PRG banks = 2 (32 KB) or 1 (16 KB, from Manifest `prg_kb`), CHR banks = 1, byte 6 bit 0 = 1 for vertical mirroring and 0 for horizontal (Manifest `mirroring`), mapper 0, bytes 7-15 zero.
3. THE Builder SHALL append `chr.bin` (exactly 8192 bytes) after the PRG data.
4. IF the linked PRG exceeds the selected size, THEN THE Builder SHALL stop with an error that names the segment and the overflow in bytes (parse the ld65 map file).
5. THE Builder SHALL print the ROM size and CRC-32, and SHALL be deterministic (same inputs → identical bytes).
6. IF `cc65`, `ca65` or `ld65` is not found, THEN THE Builder SHALL stop with an error that says which tool is missing (no automatic install).

R2 Memory map (`runtime/nrom.cfg`)
1. PRG at `$8000` (32 KB) or `$C000` (16 KB); vectors at `$FFFA` (NMI, RESET, IRQ).
2. Zero page `$00-$FF`, OAM shadow page at `$0200-$02FF` (page aligned), C stack and BSS in `$0300-$07FF`.

R3 Reset and PPU init
1. On RESET: `sei`, `cld`, disable APU frame IRQ (`$4017 = $40`), DMC IRQ off (`$4010 = 0`), stack `$FF`, PPU off (`$2000 = 0`, `$2001 = 0`), wait two vblanks via `$2002` bit 7, clear RAM, hide all OAM sprites (Y = `$FF`).
2. Upload palettes (32 bytes at `$3F00`), screen 0 nametable + attribute (1024 bytes at `$2000`), then enable NMI and rendering.
3. PPUCTRL: NMI on (bit 7), **8x16 sprites (bit 5 = 1)**, BG pattern table `$0000` (bit 4 = 0), increment 1.
4. PPUMASK: show BG and sprites including the left 8 px.

R4 NMI (once per frame)
1. OAM DMA: `$2003 = 0`, `$4014 = $02`.
2. Apply the VRAM update queue (bounded, at most 64 bytes per frame), then write the scroll **last**: `$2005 = 0` twice and the nametable bits of PPUCTRL.
3. Set a frame flag that `wait_frame()` waits for. No game logic inside NMI.

R5 Runtime API (C, `runtime/chrono.h`)
- `void wait_frame(void);`
- `void pad_update(void);` reads controller 1 once per frame (strobe `$4016`, 8 reads); `btn(b)` = held, `btnp(b)` = pressed this frame (`now & ~prev`). Edge detection is computed once in `pad_update`, never by a second read in the same frame.
- `void meta_spr(unsigned char x, unsigned char y, const unsigned char *meta);` appends hardware sprites to the OAM shadow; writes OAM Y = `y - 1` and skips the call when the shadow is full (64 sprites). `oam_clear()` hides the rest at the start of each frame.
- `void text(unsigned char col, unsigned char row, const char *s);` queues the string bytes directly (tile index = ASCII code).
- `void load_screen(unsigned char n);` rendering off, write nametable N, rendering on at the next vblank.
- `void sfx(unsigned char id);` simple pulse/noise effects.
- No zero-length VRAM writes; every queued write has length 1-32.

R6 Boot test (property of the whole pipeline)
1. THE test SHALL build a sample game, load the `.nes` into `web/nes.js` under Node, run 30 frames with no input, and compare the BG of frame 30 with `render_nes_frame` of screen 0 (sprites excluded). They SHALL match pixel for pixel.
2. THE test SHALL press Start for one frame and check that the game state changes (e.g. a known sprite moves), proving input and OAM DMA work.

## 4. Pitfalls to keep in steering (from the earlier prototype)

- `vram_write` with length 0 writes 64 KB. Never queue length 0.
- Polling the pad twice in one frame breaks `btnp`.
- Any zero-page symbol shared between C and asm must be declared in C with `#pragma zpsym`.
- `$3F10` mirrors `$3F00` (see section 0).
- Sprites appear one line below their OAM Y.
- Writes to `$2006/$2007` outside vblank corrupt the screen; only `load_screen` (rendering off) may write large blocks.
