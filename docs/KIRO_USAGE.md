# How Kiro was used

## In one paragraph

Chronomicon was built **spec-first**. For each part of the pipeline we wrote a short seed (`docs/*_seed.md`) with the
goal, scope, hardware facts and the traps we already knew about. Kiro turned each seed into a full spec
(requirements in EARS form, a design, a task list), then implemented the tasks one by one, writing unit tests and
**property-based tests** as it went. Six **steering** files kept the project rules in front of Kiro in every session:
what the product is, the contest rules, the toolchain limits and twelve hardware pitfalls that cost us time before.
A second AI (Claude) acted as reviewer for the hardware facts and drew the demo art; Kiro owns the converter, the ROM
builder, the runtime and the tests.

## Numbers (from `.kiro/specs/*/tasks.meta.json`)

| Spec | Workflow | Tasks done | Property tests (Kiro PBT status) | Dates |
|---|---|---|---|---|
| `asset-converter` | requirements-first | 66 / 66 | 12, all passed | 2026-11-17 to 11-19 |
| `rom-builder` | requirements-first | 40 / 65 (the 25 left are optional extra tests) | 3, all passed | 2026-11-19 |

Requirements: about 37 KB per spec. Designs: 61 KB and 73 KB. 19 test modules in `tests/`.

## Features used

### Specs

- Two specs, `.kiro/specs/asset-converter` and `.kiro/specs/rom-builder`, both requirements-first.
- We did not let Kiro start from a one-line prompt. Each spec started from a seed that already fixed the scope
  (for example: flip-screen rooms instead of scrolling, sound effects only, NROM only) so that the generated
  requirements could not drift into features we could not finish before the deadline.
- The seed for the ROM builder began with a bug that the first spec had shipped (the `$3F10` palette mirror
  overwriting the backdrop color). Kiro added it to the converter spec as task 17, fixed it, and added a property test
  for the invariant ("byte 0 of every palette is the backdrop").
- Checkpoint tasks ("ensure all tests pass", "the sample ROM builds and runs in tinynes") gave us natural points to
  stop and review.

### Steering (`.kiro/steering/`)

| File | Inclusion | Why |
|---|---|---|
| `product.md` | always | What Chronomicon is, who it is for, non-goals, the no-trademark rule |
| `kiroween-rules.md` | always | Contest rules the final repo must satisfy (keep `/.kiro`, licence, video rules) |
| `tech.md` | always | Toolchain, environment hard rules, the "8-bit subset", 12 known pitfalls, testing expectations |
| `language.md` | always | Talk to us in Japanese, write code and docs in English (the repo is judged in English) |
| `browser-player.md` | fileMatch `web/**` | API and limits of the bundled emulator, loaded only when Kiro touches the player |
| `hardware.md` | manual | Cartridge board and writer pin-out, pulled in only for hardware questions |

The pitfalls list in `tech.md` is the most valuable part: each line is a mistake from an earlier prototype
(for example "`vram_write(ptr, 0)` writes 64 KB", "sprites appear one line below their OAM Y"). Putting them in steering
means every Kiro session starts with them instead of rediscovering them.

The environment rules mattered too: Kiro must use the project `.venv`, must not download or install toolchains, and
must ask before adding a dependency.

### Property-based testing

Kiro wrote Hypothesis properties for every converter stage and tracked them in the spec (15 properties, all passing):

- CHR encode / decode round trip; duplicate sprite pairs are removed without changing the image
- at most 4 colors per palette after quantisation; palette map consistency
- nametable values always inside the CHR range; attribute values always 0-3
- metasprite flip symmetry and flip involution (flipping twice gives the original)
- `.pyxres` loader round trip; font round trip
- iNES header and ROM layout; PRG overflow detection
- password round trip (the C password code is compared with a Python oracle)

`tests/conftest.py` has two Hypothesis profiles: `dev` (25 examples, fast while Kiro iterates) and `ci` (200).

### Testing on the real target, headless

The ROM tests run the built `.nes` in our own emulator under Node (`tests/node/rom_server.js`) and compare frames with a
Python reference renderer, so "it boots and the first screen looks right" is a test, not a manual check.

### Hooks (`.kiro/hooks/`)

Two agent hooks keep the loop short when Kiro edits code:

| Hook | Trigger | Action |
|---|---|---|
| `converter-tests` | Kiro saves a file under `converter/` or `builder/` | runs the fast pytest profile (`HYPOTHESIS_PROFILE=dev`, stop at the first failure) |
| `rebuild-demo-rom` | Kiro saves the demo game (`samples/ten_years_vow/*.c`, `manifest.json`, `.pyxres`) | runs `chrono build` and copies the ROM to `web/roms/`, so the browser player always plays the latest build |

We added the hooks late in the project, after the specs were done; most of the converter and builder was written
before they existed.

### MCP

Not used. No MCP servers are configured for this workspace; everything Kiro needed was in the repository, the
steering files and the local toolchain.

### IDE / CLI

Kiro IDE. Each spec was generated in the IDE and its tasks were run from the spec's task list
(`.kiro/specs/*/tasks.meta.json` records 291 task executions across the two specs).

## How we split the work

| Part | Made by |
|---|---|
| Asset converter (`converter/`) | Kiro, from the seed and spec |
| ROM builder (`builder/`) and runtime (`runtime/`) | Kiro, from the seed and spec |
| Tests (`tests/`) | Kiro |
| Spec seeds, steering, hardware facts | the team, reviewed with Claude |
| Demo pixel art (`samples/ten_years_vow/art/`) | Claude |
| Demo game code (`samples/ten_years_vow/main.c`) | Claude, written against Kiro's runtime API (`runtime/chrono.h`) |
| Browser player / emulator (`web/nes.js`) | Claude, used as a tool |
| Cartridge board and writer | the team with Claude; deliberately outside the Kiro scope |

## What went wrong, and what we changed

- **The palette mirror bug.** The first spec shipped a converter whose sprite palettes overwrote the backdrop color
  (`$3F10` mirrors `$3F00` on the real chip). We found it on screen, wrote the fix and the hardware fact at the top of
  the ROM builder seed, and Kiro turned it into task 17 of the converter spec with a property test
  ("byte 0 of every palette is the backdrop") so it cannot come back.
- **Deadline over polish.** On 2026-11-20 we stopped asking Kiro for more tests and had it finish the end-to-end
  path first (convert, build, boot test in the headless emulator). The 25 optional test tasks still open in the
  ROM builder spec are open on purpose.
- **"Works in the emulator, white screen on the console."** The first ROM burned to our cartridge showed a white
  screen. Small test ROMs (a color cycle for the program chip, stripes for the graphics chip, and a walking address
  test) showed that the program chip saw address line A9 wrong. The cause was two crossed wires (A9/A11) in our
  hand-wired chip adapter for the flash writer, not Kiro's ROM: the verify step passed because the writer read back
  through the same crossed wires. After fixing the adapter, the unchanged ROM ran on the first try.

## If we did it again

- Write the hardware pitfalls into steering on day one. Every session then starts with them.
- Start each spec from a short seed with a fixed scope, not from a one-line prompt. Specs that start narrow finish.
- Test the real target early. A headless emulator test is cheap; a test ROM on real hardware finds what no
  emulator will.
