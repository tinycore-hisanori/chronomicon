# Implementation Plan: rom-builder

## Overview

This plan builds the `chrono build` pipeline (Python package `builder/`), the C and 6502 Runtime in `runtime/`, and the verification harness (Node driver around `web/nes.js`, static checks, Hypothesis property tests, Boot_Test). Work proceeds from pure Python modules, to the Runtime sources, to orchestration and the CLI, to the test harness, to the tests that need a built ROM.

Ground rules for every task:

- Python 3.12, always through `.venv\Scripts\python -m ...`. Never install or download tools or dependencies. If a re-install of the project itself (`pip install -e .`) is needed for the `chrono` script entry, ask the user first; tests call `builder.cli.main` in-process.
- cc65 2.19 (`C:\cc65\bin`) and Node v24 are already installed. `web/nes.js` (tinynes) already exists and MUST NOT be modified.
- Do not modify `requirements.md` or `design.md`.
- Property tests use the Hypothesis profiles from `tests/conftest.py` (`dev` / `ci`). Never hard-code `max_examples` in a test or in `@settings`.
- Each property test carries the comment lines `# Feature: rom-builder, Property N: <title>` and `# Validates: Requirements X.Y`.
- Tests that need Node or cc65 skip with a clear message when the tool is missing (set `CHRONO_REQUIRE_TOOLCHAIN=1` to turn skips into failures).

## Tasks

- [ ] 1. Builder core modules
  - [ ] 1.1 Create the `builder/` package skeleton and packaging
    - Create `builder/__init__.py` and `builder/errors.py` (`BuildError(Exception)` with `message` and `exit_code = 1`).
    - Update `pyproject.toml` so `[tool.setuptools.packages.find]` includes `converter*` and `builder*`. Leave the `chrono` script entry for task 6.2.
    - Add `read_manifest_table = _read_raw` to `converter/manifest.py` as a public alias with no behaviour change.
    - _Requirements: 1.10, 1.11, 1.12_

  - [ ] 1.2 Implement `builder/config.py`
    - `BuildConfig` frozen dataclass with derived paths (`assets_dir`, `obj_dir`, `rom_path`, `map_path`, `label_path`, `prg_start`, `prg_size`).
    - `validate_name(name)`: regex `^[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}$`, no trailing dot or space, no Windows device names (also with an extension), every failure is a `BuildError` whose message contains the word `name`.
    - `load_build_config(manifest_path, build_dir, runtime_dir)`: read the table through `read_manifest_table`; parse `name`, `game_sources` (relative to the manifest directory, `.c`/`.s` only, must exist, unique stems), `prg_kb` (16 or 32, default 32), `mirroring` (default `vertical`). Errors name the field. `name` is validated before anything else.
    - _Requirements: 1.1, 1.2, 1.8, 1.9_

  - [ ] 1.3 Implement `builder/tools.py`
    - `ToolPaths` dataclass, `find_tools(which=shutil.which, environ=os.environ)` for `cc65`, `ca65`, `ld65`; a missing tool raises `BuildError` naming the tool and stating that nothing is installed. Library directory from `CC65_HOME/lib` or `<cc65 bin>/../lib`; `none.lib` must exist. A version other than 2.19 prints a warning on stderr and continues.
    - `run_tool(argv, what)`: list arguments (no shell), stdout/stderr decoded as UTF-8 with `errors="replace"`, non-zero exit raises `BuildError` with the tool name, file and stderr.
    - _Requirements: 1.1, 1.7_

  - [ ] 1.4 Implement `builder/ines.py`
    - `build_ines_header(prg_kb, mirroring)` returns the 16 bytes `4E 45 53 1A`, `prg_kb // 16`, `1`, `flags6`, then 9 zero bytes.
    - `assemble_rom(prg, chr_bin, prg_kb, mirroring)` returns `header + prg + chr_bin` and raises `ValueError` when `len(prg) != prg_kb * 1024` or `len(chr_bin) != 8192`.
    - _Requirements: 1.2, 1.3_

  - [ ] 1.5 Implement `builder/linkmap.py`
    - `Segment` and `Overflow` dataclasses, `parse_segment_list(text)`, `find_overflow(segments, prg_start, prg_size)` (PRG segments `STARTUP`, `CODE`, `RODATA`, `ONCE`, `LOWCODE`), `parse_ld65_overflow(stderr)` with quote-tolerant regex, `parse_labels(text)` for `-Ln` lines `al <hex> .<name>`.
    - _Requirements: 1.4_

  - [ ] 1.6 Implement `builder/glue.py`
    - `write_glue(assets_dir) -> GlueInfo`: write `assets_data.c` (single `#include "assets.h"`), `assets_decl.h` (one `extern const unsigned char NAME[];` per definition found with the multi-line regex `^const unsigned char (\w+)\[\d*\]\s*=`), and `screens.s` (`_screen_count`, `screen_nt_lo/hi`, `screen_at_lo/hi` tables in `RODATA`).
    - `BuildError` for zero screens, a gap in `nametable_N.s` numbering (not 0..N-1), or more than 255 screens.
    - _Requirements: 1.1, 8.1_

- [ ] 2. Builder pure tests
  - [ ] 2.1 Write property test for iNES header and ROM layout
    - **Property 1: iNES header and ROM layout**
    - Add to `tests/test_builder_pure.py`. Generate `prg_kb` in {16, 32}, `mirroring`, random PRG bytes of the right length and random 8192 CHR bytes. Also add one example test for each of the four (`prg_kb`, `mirroring`) combinations and the `ValueError` cases.
    - **Validates: Requirements 1.2, 1.3**

  - [ ] 2.2 Write property test for manifest name validation
    - **Property 2: Manifest name validation**
    - Add to `tests/test_builder_pure.py`. Arbitrary text, plus non-string and missing-field cases; add example tests for `load_build_config` (defaults, relative `game_sources`, duplicate stems, bad `prg_kb`, bad `mirroring`, `name` checked first).
    - **Validates: Requirements 1.8, 1.9**

  - [ ] 2.3 Write property test for PRG overflow detection
    - **Property 3: PRG overflow detection**
    - Add to `tests/test_builder_pure.py`. Render generated segment layouts as an ld65 "Segment list", parse back, compare `find_overflow`; render the stderr warning with ASCII and UTF-8 curly quotes and compare `parse_ld65_overflow`. Add an example test using the measured ld65 output (`RODATA 008096 011CD5 009C40 00001`, overflow 7388) and `parse_labels`.
    - **Validates: Requirements 1.4**

  - [ ] 2.4 Write unit tests for tool discovery and glue generation
    - Add to `tests/test_builder_pure.py`. `find_tools` with an injected `which` (missing tool names the tool; `none.lib` missing; `CC65_HOME`). `write_glue` on a small `assets.h` text and on synthetic `nametable_N.s` files (extern list, `screens.s` content, gap and zero-screen errors).
    - _Requirements: 1.1, 1.7, 8.1_

- [ ] 3. Checkpoint - builder core
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. Runtime configuration and assembly
  - [ ] 4.1 Create `runtime/nrom.cfg`
    - One linker config exactly as in the design: weak `CHRONO_PRG_START` (`$8000`), `CHRONO_PRG_SIZE` (`$7FFA`), `__STACKSIZE__`; memory areas `ZP`, `OAM`, `RAM` (`$0300-$06FF`), `STACK` (`define = yes`), `PRG` (`fill = yes`, `fillval = $FF`), `VEC` (`$FFFA`); the segments `ZEROPAGE`, `OAM` (`align = $100`), `BSS`, `DATA`, `STARTUP`, `CODE`, `RODATA`, `VECTORS`.
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

  - [ ] 4.2 Create `runtime/chrono.h`, `runtime/chrono_zp.h` and `runtime/zp.s`
    - `chrono.h`: includes `assets_decl.h`; `BTN_*` constants (A=1 ... RIGHT=128); `pad_now`, `pad_pressed`, `btn`/`btnp` macros; prototypes for `wait_frame`, `pad_update`, `oam_clear`, `meta_spr`, `text`, `load_screen` (`__fastcall__`), `screen_count`, `sfx`, `password_encode`, `password_decode`; `SFX_*` ids 0 to 3; `PASSWORD_MAX_STATE_LEN` 8 and `PASSWORD_BUF_SIZE` 15, both documented.
    - `chrono_zp.h`: `extern` declarations and `#pragma zpsym` for `frame_flag`, `vram_ready`, `vq_head`, `vq_tail`, `ppuctrl_shadow`, `ppumask_shadow`.
    - `zp.s`: `.segment "ZEROPAGE"` definitions with `.exportzp` for exactly those six symbols.
    - _Requirements: 5.1, 5.4, 9.1, 9.7, 10.3, 12.1, 12.2_

  - [ ] 4.3 Create `runtime/crt0.s` (RESET)
    - Exact order: `sei`, `cld`, `$4017=$40`, `$4010=0`, `txs` with `$FF`, `$2000=0`, `$2001=0`; two vblank polls on `$2002` bit 7; RAM clear `$0000-$07FF` with no `jsr` and no stack use; set `c_sp` (`.importzp c_sp`) to `__STACK_START__ + __STACK_SIZE__`; `zerobss`, `copydata`; hide all 64 OAM entries (`$FF`); `$4015 = $0B`; 32-byte palette upload `palette_bg` then `palette_sprite` at `$3F00`; `screen_upload` with A = 0; `bit $2002`, `$2005` twice with 0; `ppuctrl_shadow = $A0` to `$2000`; `ppumask_shadow = $1E` to `$2001`; `jsr _main`; halt loop.
    - Export `__STARTUP__ : absolute = 1`, `reset_handler`, `nmi_handler`, `irq_handler`; `irq` is `rti`; `VECTORS` segment with NMI, RESET, IRQ.
    - Put the palette upload inside `.proc reset` so static rule S2 can locate it.
    - _Requirements: 2.3, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 9.4, 10.5, 10.6_

  - [ ] 4.4 Create `runtime/nmi.s` (NMI handler and `vram_apply`)
    - Reserve `nmi_budget` and `nmi_len` at the top of the file in `.segment "ZEROPAGE"` without exporting them.
    - `nmi`: save A, X, Y; `$2003 = 0`; `$4014 = $02`; if `vram_ready` then `jsr vram_apply` and clear `vram_ready`; `bit $2002`; `$2005` twice with 0; `$2000 = ppuctrl_shadow`; `frame_flag = 1`; restore Y, X, A; `rti`.
    - `.proc vram_apply`: index-based consumer from the design (budget 64 payload bytes, whole entries only, `; ZEROLEN-GUARD` marker followed by `beq`, queue discarded on a zero-length entry, `vq_head`/`vq_tail` reset when drained). No cc65 zero-page symbol, no `jsr` to C or library code.
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 7.5, 10.1, 10.5, 10.7_

  - [ ] 4.5 Create `runtime/screen.s` (`screen_upload` and `load_screen`)
    - `.proc screen_upload` (A = screen index): sets `$2006` to `$20,$00`, writes 960 nametable bytes and 64 attribute bytes to `$2007` using the `screen_nt_*` / `screen_at_*` tables (may use `ptr1`/`ptr2`; it is not in the NMI call graph).
    - `_load_screen` (`__fastcall__`): range check against `_screen_count`; `jsr _wait_frame`; clear PPUCTRL bit 7; PPUMASK = 0; `screen_upload`; empty the queue and clear `vram_ready`; poll vblank; scroll 0 twice; restore `ppuctrl_shadow` and `ppumask_shadow`.
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 10.5_

- [ ] 5. Runtime C sources
  - [ ] 5.1 Create `runtime/runtime.c` and `runtime/pad.c`
    - `runtime.c`: `wait_frame()` (`vram_ready = 1; frame_flag = 0;` spin, then `sfx_update()`), the `vq_dropped` counter; include `chrono_zp.h`.
    - `pad.c`: `JOY1` macro for `$4016`, `pad_update()` (strobe 1 then 0, eight reads, LSB-first assembly, `pad_pressed = now & ~prev`), `pad_now`, `pad_pressed`. `$4016` appears only in this file and `JOY1` is read only inside `pad_update`.
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 7.6, 10.2_

  - [ ] 5.2 Create `runtime/oam.c`
    - `oam[256]` in segment `OAM` (`#pragma bss-name (push, "OAM")`), `oam_count`, `oam_clear()` (Y = `$FF` for all 64 entries, count = 0), `meta_spr()` (count groups up to the terminator 128; skip the whole call when `oam_count + n > 64`; write Y, tile, attr, X with `y + dy - 1` and `x + dx` modulo 256).
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 10.4_

  - [ ] 5.3 Create `runtime/text.c`
    - `vq_buf[128]` (exported for `nmi.s` and `screen.s`), `vramq_push(addr, src, len)` with the first-statement guard `if (len == 0 || len > 32) return;`, and `text(col, row, s)` implementing the design split rule: ignore `col >= 32` or `row >= 30`, empty string queues nothing, truncate at `$23BF`, 32-byte chunks with consecutive addresses, free-space check `n + 3 * ceil(n / 32) <= 128 - vq_tail`, otherwise drop the whole string and increment `vq_dropped`.
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 10.1_

  - [ ] 5.4 Create `runtime/sfx.c`
    - `sfx(id)` with the register tables for `SFX_JUMP`, `SFX_HIT`, `SFX_SELECT`, `SFX_ITEM` (writes only in `$4000-$4007` and `$400C-$400F`), unknown ids return without any write, `sfx_timer` and `sfx_update()` for the second note of `SFX_ITEM` (writes only when the timer is non-zero).
    - _Requirements: 9.2, 9.3, 9.5, 9.6, 9.7_

  - [ ] 5.5 Create `runtime/password.c`
    - Alphabet `ABCDEFGHJKLMNPQRSTUVWXYZ23456789`; `password_encode` (D = ceil(8 * len / 5) data symbols, bits packed MSB first with zero padding, checksum symbol = sum mod 32, NUL terminator; invalid `len` writes an empty string); `password_decode` with the validation order from the design (len range, bounded length count equal to N, alphabet check, checksum, rebuild into a local `tmp[8]`, copy to `state` only on success, return 1 or 0). No libc headers; no host-only constructs.
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7_

- [ ] 6. Build orchestration, CLI and ROM fixtures
  - [ ] 6.1 Implement `builder/build.py`
    - `BuildResult` and `build(config, tools=None, log=print)`: load config, find tools, delete Builder-owned `<build>/assets`, `<build>/obj` and `<name>.nes`, run `run_pipeline`, `write_glue`, compile and assemble in the fixed object order with the exact command lines from the design, link with `nrom.cfg` (add `-D CHRONO_PRG_START=0xC000 -D CHRONO_PRG_SIZE=0x3FFA` for 16 KB; `-m` map, `-Ln` labels), handle ld65 failure through `find_overflow` then `parse_ld65_overflow` (message with segment and bytes, no `.nes`), check `prg.bin` and `chr.bin` sizes, assemble the ROM, write through `<name>.nes.tmp` and `os.replace`, print `build/<name>.nes: <size> bytes, crc32=<8 hex digits>`.
    - Convert `ConversionError`/`OSError` into `BuildError`; no timestamps in outputs.
    - _Requirements: 1.1, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9_

  - [ ] 6.2 Implement `builder/cli.py` and the `chrono` script entry
    - `main(argv)` dispatcher: `convert` forwards the remaining arguments unchanged to `converter.converter.main`; `build` parses `<manifest> [-o BUILD_DIR] [--runtime-dir DIR]` (default build dir `build`, default runtime dir next to the package) and calls `build`; `BuildError` prints `error: ...` on stderr and returns 1; usage errors return 2; `-h/--help` returns 0.
    - Set `chrono = "builder.cli:main"` in `pyproject.toml`. Leave `converter/__main__.py` unchanged.
    - _Requirements: 1.5, 1.10, 1.11, 1.12_

  - [ ] 6.3 Create ROM fixtures, the sample game and mailbox ROM sources
    - `tests/rom_fixtures.py`: build the deterministic project in a temp directory using `tests/pyxres_writer.py` (two screens that clearly differ, at least 3 distinct BG tiles using at least 2 BG palettes, font mapped, one 8x16 sprite `player` with one hardware sprite at offset (0, 0)) and write three manifests (`boot_test`, `password_rom`, `runtime_rom`) with `name`, `game_sources`, `prg_kb = 32`, `mirroring = "vertical"` plus the converter keys. Never check a `.pyxres` into the repository.
    - `samples/boot_test/main.c`: the sample loop from the design (`wait_frame`, `pad_update`, `btnp(BTN_START)` adds 16 to `px`, `oam_clear`, `meta_spr(px, 120, metasprite_player)`).
    - `tests/rom/password_rom.c` and `tests/rom/runtime_rom.c`: the mailbox ROMs exactly as specified in the design (`pw_cases`, `pw_count`, `pw_ctrl`; `rt_cmd`, `rt_done`, `rt_arg`, `rt_meta`, `rt_str`, `rt_dump`, `cnt_held`, `cnt_edge`, commands META, TEXT, TEXT_DUMP, LOAD_SCREEN), with a main loop that calls `wait_frame(); pad_update();` every frame.
    - _Requirements: 11.1, 11.4, 12.9_

  - [ ] 6.4 Write unit tests for CLI routing and exit codes
    - Add to `tests/test_builder_pure.py`: `convert` forwards its arguments unchanged to the Converter main (monkeypatched), `python -m converter` still runs through `converter.__main__` unchanged, `build` returns 0 on success (monkeypatched `build`) and prints size and CRC-32, `BuildError` gives exit code 1 with `error:` on stderr, unknown subcommand and missing manifest give exit code 2, old form `chrono manifest.json` is a usage error.
    - _Requirements: 1.5, 1.9, 1.10, 1.11, 1.12_

- [ ] 7. Node driver and pytest harness
  - [ ] 7.1 Create `tests/node/rom_server.js`
    - Persistent process requiring `../../web/nes.js` (do not modify that file). Line-delimited JSON on stdin/stdout with ops `load` (base64 ROM) and `run`. Each `run` creates a fresh `new NES()` and loads the cached ROM. Steps support `writes` (CPU RAM, addr < 0x800, applied before the frames), `hold` (int or per-frame list, applied with `setButton(0, bit, bool)` before each `frame()`), `frames`, `reads` (`name`, `addr`, `len`), `snap` (`index_buffer`, `oam`, `vram`, `pal`). Tracing wraps `nes.write`: `ppu_data` per-frame `$2007` counts, `io` writes to `$2000-$2007` and `$4000-$4017` with the frame index, `apu` writes to `$4000-$4017`. Errors return `{"ok":false,"error":...}` and the process keeps running.
    - _Requirements: 11.1, 11.8_

  - [ ] 7.2 Create `tests/rom_harness.py`
    - `need_node()` (returns `shutil.which("node")` or `pytest.skip("Node.js not found on PATH ...")`, never installs anything), `RomRunner` context manager (one Node process per ROM, `run(steps, trace=None) -> list[StepResult]`, raises with the driver's error message on `ok: false`), `read_labels(lbl)` using `builder.linkmap.parse_labels`.
    - _Requirements: 11.1, 11.8, 11.9_

  - [ ] 7.3 Append session fixtures to `tests/conftest.py`
    - Keep the Hypothesis profile code unchanged. Add `rom_project`, `boot_rom`, `password_rom`, `runtime_rom` (each builds once per session through `builder.build.build` into a `tmp_path_factory` directory and returns a `BuiltRom(nes, map, lbl, build_dir)`), and `boot_runner`, `password_runner`, `runtime_runner` (started `RomRunner` per ROM). Missing cc65 tools or Node skip with a clear message; `CHRONO_REQUIRE_TOOLCHAIN=1` turns the skips into failures.
    - _Requirements: 1.1, 11.1, 11.8, 11.9, 12.9_

  - [ ] 7.4 Write unit tests for the harness
    - Create `tests/test_rom_harness.py`: `read_labels` on a sample label file, `need_node` skip message when `which` finds nothing (monkeypatched), driver protocol checks on the boot ROM (load, run with `frames`, `reads`, `writes`, `hold`, a bad request returns an error and the process stays alive).
    - _Requirements: 11.1, 11.8, 11.9_

- [ ] 8. Build integration tests
  - [ ] 8.1 Write build integration tests: success, determinism, missing tool
    - Create `tests/test_build_rom.py`: boot ROM build gives exit code 0, the files exist, printed size and CRC-32 match `zlib.crc32` of `build/boot_test.nes`; two builds of 32 KB/vertical and of 16 KB/horizontal into different directories are byte-identical; a fake PATH without `ld65` gives a non-zero exit code naming `ld65` and no `.nes`; a manifest without `name` fails before any tool runs and names `name`.
    - _Requirements: 1.1, 1.2, 1.3, 1.5, 1.6, 1.7, 1.8, 1.9_

  - [ ] 8.2 Write build integration test: PRG overflow
    - Add to `tests/test_build_rom.py`: a game source with an oversized `const` array makes the build fail with a non-zero exit code, no `.nes` file (also no stale one), and a message containing the segment name and the overflow in bytes.
    - _Requirements: 1.4_

  - [ ] 8.3 Write memory map and vector tests
    - Add to `tests/test_build_rom.py` using the boot ROM, its map and label file, plus one 16 KB build: last 6 PRG bytes equal the little-endian addresses of `nmi_handler`, `reset_handler`, `irq_handler`; PRG starts at `$8000` (`$C000` for 16 KB); every `ZEROPAGE` range inside `$00-$FF`; `OAM` starts at `$0200` and is at most 256 bytes; `BSS` and `DATA` inside `$0300-$06FF`; `__STACK_START__ = $0700` and `__STACK_START__ + __STACK_SIZE__ = $0800`; no two segment ranges overlap.
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

- [ ] 9. Checkpoint - the Runtime builds a ROM
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 10. Static checks S1 to S6
  - [ ] 10.1 Implement rule functions and tests for S1 to S5 plus S6
    - Create `tests/static_rules.py` (comment stripping for `.s`, `.c`, `.h`; `.proc` block and brace matching; `find_register_uses(text, token)`; call-graph builder and checker) and `tests/test_runtime_static.py`. Implement rules S1 (`4016` only in `pad.c`, `JOY1` only inside `pad_update`), S2 (`$2006/$2007` only in `crt0.s` inside `.proc reset`, `nmi.s` inside `.proc vram_apply`, `screen.s` inside `.proc screen_upload`; never in `.c`/`.h`), S3 (every `.importzp`/`.exportzp` name outside the cc65 set has a `#pragma zpsym`), S4 (`vramq_push` guard `if (len == 0` first, `; ZEROLEN-GUARD` followed by `beq` in `vram_apply`), S5 (NMI-reachable nodes contain no `ptr1-4`, `tmp1-4`, `sreg`, `regsave`, `c_sp`, `regbank`, no external library target, `screen_upload` not reachable) and S6 (no `jsr`/`jmp` to a C function from the NMI set).
    - Run every rule on the real `runtime/` sources and add positive and negative tests of each rule function on small synthetic strings.
    - _Requirements: 5.7, 10.1, 10.2, 10.3, 10.5, 10.7_

  - [ ] 10.2 Write property test for the NMI call graph checker
    - **Property 16: The NMI call graph never touches cc65 zero page or C code**
    - Add to `tests/test_runtime_static.py`. Generate routine sets with random `jsr`/`jmp` edges, random instruction text and a random subset of nodes with a forbidden zero-page reference, a `jsr` to a C function, or an external library symbol. Assert a violation is reported if and only if such a node is reachable from `nmi`, and that unreachable nodes never cause one. Add an assertion that the real `runtime/*.s` and `runtime/*.c` produce no violation.
    - **Validates: Requirements 10.7**

  - [ ] 10.3 Write static structure tests
    - Add to `tests/test_runtime_static.py`: two `$2002` bit 7 polls come before the RAM clear in `reset`, no `jsr` inside the clear, the NMI saves and restores A, X and Y, `nmi.s` imports no C symbol, `$2003` is written before `$4014` in `nmi`, the scroll writes are the last PPU writes of `nmi`, `chrono.h` declares all API functions and defines the eight `BTN_*`, four `SFX_*` constants, `PASSWORD_MAX_STATE_LEN` 8 and `PASSWORD_BUF_SIZE` 15, and `pad.c` is the only file with a `$4016` read.
    - _Requirements: 3.1, 3.2, 3.3, 4.1, 4.4, 4.7, 5.1, 5.4, 9.1, 9.7, 10.2, 12.1, 12.2_

- [ ] 11. Password oracle and property tests
  - [ ] 11.1 Create `tests/password_ref.py`
    - `ALPHABET`, `data_len(n)`, `encode(state: bytes) -> str`, `decode(pw: str, n: int) -> bytes | None` with the same step order as the C design (len range, length N, alphabet, checksum, rebuild; padding bits ignored).
    - _Requirements: 12.3, 12.4, 12.5, 12.6, 12.7, 12.9_

  - [ ] 11.2 Write property test for password round trip and shape
    - **Property 4: Password round trip and shape (oracle)**
    - Create `tests/test_password.py`. Generate `len` in 1..8 and `state` bytes; check output length `ceil(8*len/5) + 1`, alphabet membership, checksum equals the sum of the data symbols mod 32, and `decode(encode(state), len) == state`.
    - **Validates: Requirements 12.3, 12.4, 12.5, 12.6**

  - [ ] 11.3 Write property test for single-substitution detection
    - **Property 5: Password single-substitution detection (oracle)**
    - Add to `tests/test_password.py`. Any valid password, any position (data or checksum), any different alphabet symbol: `decode` fails.
    - **Validates: Requirements 12.5, 12.7**

  - [ ] 11.4 Write property test for password rejection
    - **Property 6: Password rejection and untouched state (oracle)**
    - Add to `tests/test_password.py`. Wrong length, characters outside the alphabet (lowercase, `I`, `O`, `0`, `1`, space), wrong checksum, `len` 0 or greater than 8: `decode` fails and the caller's buffer is unchanged. Add an example test that `encode` with an invalid `len` returns an empty string.
    - **Validates: Requirements 12.7**

  - [ ] 11.5 Write property test for the C password code against the oracle
    - **Property 7: C password code agrees with the oracle**
    - Add to `tests/test_password.py` using `password_rom` and `password_runner`. Resolve `_pw_cases`, `_pw_count`, `_pw_ctrl` through the label file, pack cases with `struct` format `"<BB8s16sB5x"`, generate batches of up to 16 cases (encode, decode of valid, decode of one-symbol-corrupted, decode of malformed), set `pw_ctrl = 1`, run frames until it reads 2, and compare with the oracle: identical encode strings, decode result codes, decoded bytes, and sentinel bytes unchanged on failure.
    - **Validates: Requirements 12.4, 12.5, 12.6, 12.7, 12.9**

- [ ] 12. Test models and frame comparison helpers
  - [ ] 12.1 Create `tests/models.py`
    - Pure functions `split_text(col, row, s) -> list[(addr, bytes)]` (range check, truncation at `$23BF`, 32-byte chunks), `queue_entries(chunks) -> bytes`, `model_oam(calls, blobs) -> bytes` (256-byte shadow per Requirement 6), `count_edges(pattern) -> (held, edges)`.
    - _Requirements: 6.1, 6.4, 6.6, 7.1, 7.3, 7.4, 5.5, 5.6_

  - [ ] 12.2 Create `tests/frame_compare.py`
    - `sprite_mask(oam_bytes)` (each of the 64 entries covers columns `X..X+7` and rows `Y+1..Y+16`, clipped to the frame, regardless of Y), `compare_frames(a, b, mask) -> (count, first_xy | None)` in row-major order, `read_asm_bytes(path, label)` for `nametable_N.s`, and a parser for the `assets.h` palette arrays.
    - _Requirements: 11.2, 11.3, 11.5, 11.6, 11.7, 11.10_

- [ ] 13. Boot test and PPU behaviour tests
  - [ ] 13.1 Write the Boot_Test
    - Create `tests/test_boot_rom.py`: load the boot ROM into tinynes through Node, run 30 frames with no input, read `index_buffer` and `ram[0x200..0x2FF]`; the reference frame is `render_nes_frame(chr_bin, nametable_0, attr_0, bg_pal, sp_pal, [])` with palettes from the generated `assets.h` via `upload_palette`; mask sprites in both frames; require zero differing pixels and report the count and first coordinate on failure. Then hold Start for one frame and check `ram[0x203]` is 64 before and 80 after, and PPU `oam[3]` is 80 after one more frame. Skip with a Node-missing message when Node is absent.
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8, 11.9, 11.10, 10.5_

  - [ ] 13.2 Write RESET, NMI and upload order tests
    - Add to `tests/test_boot_rom.py` using the `io` trace of the boot frames: first writes `$4017=$40`, `$4010=$00`, `$2000=$00`, `$2001=$00`; then `$4015=$0B`; first `$2006` pair `$3F,$00` followed by 32 `$2007` writes equal to `palette_bg + palette_sprite`; next `$2006` pair `$20,$00` followed by 1024 `$2007` writes equal to nametable 0 plus attribute 0; then `$2005` twice with 0, `$2000 = $A0`, `$2001 = $1E`. In steady frames the first PPU write of every NMI is `$2003 = 0` followed by `$4014 = $02`, and `$2005` x2 then `$2000` are the last PPU writes. Check that OAM DMA fills PPU `oam` from the shadow.
    - _Requirements: 3.1, 3.2, 3.5, 3.6, 3.7, 4.1, 4.4, 4.9, 9.4_

  - [ ] 13.3 Write property tests for palette upload and frame comparison
    - **Property 14: Palette upload keeps the backdrop**
    - **Property 15: Frame comparison reports the exact difference**
    - Add to `tests/test_boot_rom.py` (both pure, no ROM needed). Property 14: generated palettes with offsets 0, 4, 8, 12 of both arrays equal to `b`; `upload_palette` returns BG `[0][0] == b` and sprite entry 0 equal to `b` for all four palettes. Property 15: generated index frames and OAM shadows; `compare_frames` returns the exact count of unmasked differing positions and the first one in row-major order. Add an example test that the boot sample's own palette arrays satisfy Requirement 10.6.
    - **Validates: Requirements 10.6, 11.5, 11.6, 11.10**

  - [ ] 13.4 Write property test and example for `load_screen`
    - **Property 13: `load_screen` ignores out-of-range screens**
    - Add to `tests/test_boot_rom.py` using `runtime_rom`. For `n` in `screen_count..255`, `load_screen(n)` causes no `$2001` write, no `$2006/$2007` write, and nametable 0 (`vram[0..0x3FF]`) is unchanged. Add an example test that `load_screen(1)` makes nametable 0 equal screen 1 data, the VRAM queue is empty afterwards, rendering is back on, and at most 2 frames are blank.
    - **Validates: Requirements 8.6**

- [ ] 14. Runtime behaviour tests on the runtime ROM
  - [ ] 14.1 Write property test for `text()` queue contents
    - **Property 8: `text()` queue contents follow the split model**
    - Create `tests/test_runtime_rom.py` using `runtime_runner` and the `TEXT_DUMP` command. Generate `col` 0..31, `row` 0..29 and ASCII strings of 0 to 150 characters; compare `rt_dump` with `queue_entries(split_text(...))`, or require an unchanged queue when the string does not fit. Add an example test: an empty string leaves the queue unchanged.
    - **Validates: Requirements 7.1, 7.2, 7.3, 7.4, 10.1**

  - [ ] 14.2 Write property test for the per-frame VRAM budget
    - **Property 9: Queue application respects the per-frame budget**
    - Add to `tests/test_runtime_rom.py`. With the `ppu_data` trace: at most 64 `$2007` writes in every frame, per-frame counts are sums of whole entries, writes are in queue order, and after enough frames nametable 0 holds exactly the string bytes at the target address and the queue is empty.
    - **Validates: Requirements 4.2, 4.3, 7.5, 7.6**

  - [ ] 14.3 Write property test for `meta_spr`
    - **Property 10: `meta_spr` writes the OAM shadow according to the model**
    - Add to `tests/test_runtime_rom.py`. Generate 1 to 8 calls with metasprites of 0 to 24 groups (arbitrary signed offsets, tile, attr; `x`, `y` in 0..255); read `ram[0x200..0x2FF]` and compare with `model_oam`, including skipped calls and `$FF` Y in unused entries. Add an example test with Y offsets 0 and 8 giving OAM Y bytes `y - 1` and `y + 7`.
    - **Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 10.4**

  - [ ] 14.4 Write property test for `btn` and `btnp`
    - **Property 11: `btn` and `btnp` follow the held pattern**
    - Add to `tests/test_runtime_rom.py`. Per-frame hold patterns of 0 to 20 frames padded with idle frames; `cnt_held` equals the held frames and `cnt_edge` equals `count_edges` rising edges. Add example tests: each of the 8 buttons maps to its `BTN_*` bit, `btn`/`btnp` are false before the first `pad_update()`, and a held press gives `btnp` in exactly one frame.
    - **Validates: Requirements 5.5, 5.6, 5.7, 10.2**

  - [ ] 14.5 Write property test for `sfx`
    - **Property 12: `sfx` touches only permitted APU registers**
    - Add to `tests/test_runtime_rom.py`. For ids 0..255 with the `apu` trace over enough frames: writes only to `$4000-$4007`, `$400C-$400F`, `$4015`, never `$4010-$4013` or `$4017`; ids outside 0..3 produce no APU write. Add example tests for the register values of the four effects (channel and address set, `SFX_ITEM` second note after the timer) and `sfx_update` silence when `SFX_ITEM` is unused.
    - **Validates: Requirements 9.3, 9.5**

- [ ] 15. Final checkpoint - full suite
  - Run `.venv\Scripts\python -m pytest --durations=10` with the `dev` profile and confirm the whole suite finishes within 60 seconds. If it does not, apply the design mitigations in order (session cache of compiled Runtime objects keyed by source hash as a private `build()` option; reduce rebuilds to the boot sample; fewer frames per example) without hard-coding `max_examples`.
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- All tasks, including every property-based test task and every unit or integration test task, are required. No task is optional.
- Each task references the requirement numbers it satisfies; each property test names its design property and the requirements it validates. Static rules S1 to S6 are covered by tasks 10.1 to 10.3, and Property 16 (Requirement 10.7) by task 10.2.
- `web/nes.js` is never modified. `requirements.md` and `design.md` are not changed by this plan.
- Tests that share a file (`test_builder_pure.py`, `test_build_rom.py`, `test_runtime_static.py`, `test_password.py`, `test_boot_rom.py`, `test_runtime_rom.py`) are placed in different waves of the dependency graph.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "1.4", "1.5", "1.6", "4.1", "4.2"] },
    { "id": 2, "tasks": ["2.1", "4.3", "4.4", "4.5", "5.1", "5.2", "5.3", "5.4", "5.5", "6.1", "7.1", "11.1", "12.1", "12.2"] },
    { "id": 3, "tasks": ["2.2", "6.2", "6.3", "7.2", "10.1", "11.2"] },
    { "id": 4, "tasks": ["2.3", "7.3", "10.2", "11.3"] },
    { "id": 5, "tasks": ["2.4", "7.4", "8.1", "10.3", "11.4"] },
    { "id": 6, "tasks": ["6.4", "8.2", "11.5", "13.1", "14.1"] },
    { "id": 7, "tasks": ["8.3", "13.2", "14.2"] },
    { "id": 8, "tasks": ["13.3", "14.3"] },
    { "id": 9, "tasks": ["13.4", "14.4"] },
    { "id": 10, "tasks": ["14.5"] }
  ]
}
```
