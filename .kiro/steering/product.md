---
inclusion: always
---
# Product: Chronomicon — raise Pyxel games from the dead onto real 8-bit cartridges

## Name
**Chronomicon** (repo `chronomicon`, CLI command `chrono`). A pun on the Necronomicon: a "book of time"
that turns the clock back to 1983 and brings games back to life on dead hardware.
Tagline: *"Raise your Pyxel games from the dead — onto real 8-bit cartridges."*
Do not put console trademarks or "Pyxel" in the product name (Pyxel is mentioned only as the input format).

## What we are building
A converter that takes a game made with **Pyxel** (Python retro game engine) and produces a
standard **.nes ROM (iNES, mapper 0 / NROM)** that runs on emulators, flash carts and real
8-bit consoles from 1983 onwards.

Pipeline (end to end, all of it must work):
1. Pyxel game (`.py` + `.pyxres`) written under the "8-bit subset" rules (see `tech.md`)
2. **Asset converter** (deterministic): tiles → CHR, tilemap → nametables + attribute tables,
   16 colors → 4 palettes × 4 colors, sprites → 8x16 metasprites, Pyxel font → ASCII tiles
3. **Logic port** (AI-assisted, Kiro): Python game logic → C (cc65 + NESLib), fixed-point math
4. Build with cc65 → `.nes`
5. Verify in a headless emulator (input script → screenshots) and in the browser player
6. Optional: burn to a flash cartridge and play on real hardware

## Who it is for
- Pyxel users (large hobbyist / education community, especially in Japan) who want their game
  to run on real retro hardware or be sold as a physical cartridge
- Kids' programming workshops: "make a game, take home a real cartridge"
- Homebrew developers who prototype faster in Python than in 6502 assembly

## Hackathon context: Kiroween 2026, category **Resurrection**
"Bring a dead technology back to life": the dead tech is the 8-bit cartridge console and its
whole toolchain; we revive it with a modern engine (Pyxel) and an AI-driven porting workflow.

## Non-goals
- Not a general Python→6502 compiler. We support a documented subset and fail loudly outside it.
- No mappers other than NROM in v1 (32KB PRG + 8KB CHR).
- No commercial games, no ROMs we do not own.

## Naming and trademarks (hard rule)
- Never use console maker trademarks or logos in the UI, README title, video or images.
  Say "8-bit console", "NES-format ROM (.nes)" only as a file-format name, "1983 8-bit home console".
- Do not show console logos in the demo video. Do not use copyrighted music.
