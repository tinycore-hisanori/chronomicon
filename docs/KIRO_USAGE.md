# How Kiro was used

> Draft. Lines marked **TODO** need a fact from the team before submission.

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
means every Kiro session starts with them instead of rediscovering them. **TODO**: note any pitfall Kiro still hit.

The environment rules mattered too: Kiro must use the project `.venv`, must not download or install toolchains, and
must ask before adding a dependency. **TODO**: did Kiro ever stop and ask? One sentence if so.

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

### Hooks

**TODO** (we have not used agent hooks yet). Candidate, 10 minutes of work: a hook on save of `converter/**/*.py` that
runs the converter's fast test profile, and a manual hook "rebuild the demo ROM and copy it to `web/roms/`".

### MCP

**TODO**: say whether any MCP server was used. If none, write "not used".

### IDE / CLI

**TODO**: which Kiro surface we used (IDE? CLI? both?), and the model.

## How we split the work

| Part | Made by |
|---|---|
| Asset converter (`converter/`) | Kiro, from the seed and spec |
| ROM builder (`builder/`) and runtime (`runtime/`) | Kiro, from the seed and spec |
| Tests (`tests/`) | Kiro |
| Spec seeds, steering, hardware facts | the team, reviewed with Claude |
| Demo pixel art (`samples/ten_years_vow/art/`) | Claude |
| Demo game code (`samples/ten_years_vow/main.c`) | **TODO**: Claude (written against Kiro's runtime API) — confirm |
| Browser player / emulator (`web/nes.js`) | Claude, used as a tool |
| Cartridge board and writer | the team with Claude; deliberately outside the Kiro scope |

## What went wrong, and what we changed

**TODO**: two or three real stories, for example:

- something Kiro got wrong, how we noticed (a failing property? the ROM on screen?), and what we changed in the spec or
  steering so it did not happen again
- the decision on 2026-11-20 to stop polishing tests and finish the end-to-end path first (25 optional test tasks in the
  ROM builder spec are still open, on purpose)
- places where we fixed Kiro's code by hand

## If we did it again

**TODO**: one or two lessons (for example: write the pitfalls into steering on day one; start from seeds, not prompts).
