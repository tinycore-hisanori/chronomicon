# Chronomicon — Spec seed: `ten-years-vow` (demo game, paste into Kiro as the starting point)

Goal: a one-stage action game that shows the whole pipeline end to end — Pyxel art in, a playable `.nes` out — small enough to finish before the deadline. Castle-crawler style: a princess knight returns to the castle that a demon took ten years ago.

## 0. What already exists (do not regenerate)

- `samples/ten_years_vow/ten_years_vow.pyxres` — all art. **Made with Claude** from `samples/ten_years_vow/art/make_tyv_assets.py` (text-grid pixel art, Pyxel 3). Say so in the README credits.
- `samples/ten_years_vow/manifest.json` — converts cleanly with the current converter (checked: 58 BG tiles, 14 sprites, 5 screens, no attribute conflicts).
- `docs/images/tyv_preview.png` — what every screen and sprite looks like after conversion.
- Kiro writes `samples/ten_years_vow/main.c` (and more `.c` files if needed, listed in `game_sources`).

## 1. Screens (from the Manifest, numbered as the converter numbers them)

| Screen | Content | HUD rows 0-3 |
|---|---|---|
| 0 | Title: night sky, moon, castle. Text rows 9-16 are empty sky for `text()` | sky (title tilemap) |
| 1 | Room 1 "Entrance": door at left, 2 windows, crate, pillar at right | stone HUD with a line on row 3 |
| 2 | Room 2 "Banner hall": 3 banners, planks at (4..9, y=18), (14..17, y=14), (22..27, y=18) in tiles | same |
| 3 | Room 3 "Spike corridor": spike pit tiles 10..21 on the floor, planks at (12..13, y=20) and (18..19, y=16) | same |
| 4 | Room 4 "Throne room": moon window, carpet, boss | same |

Floor: the top of the floor tiles is pixel y = 208 (tile row 26). A 32-px-tall sprite standing on the floor has display y = 176. A plank at tile row R is standable at pixel y = 8*R (sprite y = 8*R - 32).

Text uses the font in tiles `0x20-0x7E`; on stone and sky palettes the glyphs are white. Write HUD text with `text()` only when a value changes (the queue applies at most 64 bytes per frame).

## 2. Sprites (names from the Manifest; each has a `_flip` version for facing left)

| Name | Size | Use |
|---|---|---|
| `knight_idle`, `knight_walk1`, `knight_walk2`, `knight_jump`, `knight_attack` | 16x32 | player |
| `slash` | 16x16 | sword hitbox, drawn in front of the player at chest height (+16 px down) |
| `skeleton_a`, `skeleton_b` | 16x32 | walking enemy, 2-frame walk |
| `bat_a`, `bat_b` | 16x16 | flying enemy, 2-frame flap |
| `demon_a`, `demon_b` | 32x32 | boss, 2-frame idle |
| `heart` | 8x16 | pickup: +2 HP |
| `fireball` | 8x16 | boss projectile |

Initial objects per room come from `_screenN_objects` (x, y, metasprite index, `$ff` end). Use them as spawn points.

Hardware sprite budget: at most 8 sprites on one scanline. Worst case is the boss (4 wide) + player (2) + fireball (1) = 7. Keep at most 2 bats on screen.

## 3. Rules (keep them simple; numbers are starting values to tune)

- **States**: `TITLE` → (Start) `PLAY` room 1 / (Select) `PASSWORD_ENTRY` → `PLAY` → `BOSS` → `ENDING`. HP 0 → `GAME_OVER`, which shows the password for the current room.
- **Player**: walk 1 px/frame; jump with A (velocity −4.0 px/frame, gravity +0.25 px/frame², max fall 4.0) using 8.8 fixed point; attack with B (12 frames of `knight_attack` + `slash`, cannot walk while attacking). Facing left uses the `_flip` metasprites.
- **Collision**: per-room platform table in C (floor + planks as rectangles). No tile collision map in v1.
- **Rooms**: walking off the right edge calls `load_screen(next)` and places the player at x = 8. The left edge of room 1 is a wall (the door). Rooms 2-4 can be left to the left (back to the previous room, player at x = 232).
- **Spikes** (room 3, x 80..175 on the floor): touching = 2 damage and a bounce.
- **Enemies**: skeleton walks back and forth between two x limits (2 HP, touch = 1 damage). Bat flies toward the player in a zigzag (1 HP). Defeated enemies drop a heart with 1 in 3 chance.
- **Boss** (room 4, 16 HP): steps toward the player, every 90 frames throws a fireball horizontally; flashes for 30 frames when hit. Defeat → `ENDING`.
- **Damage**: player HP 8, 60 frames of invincibility (blink every 4 frames) and a 16 px knockback.
- **HUD** (rows 1-2): `VOW-1  HP:========` and, in room 4, `BOSS :========`. Bar characters are ASCII.
- **Sound**: `SFX_JUMP` on jump, `SFX_HIT` when anything takes damage, `SFX_ITEM` on heart pickup, `SFX_SELECT` on menu moves.

## 4. Password (the runtime's `password_encode` / `password_decode`)

- State bytes: `[room 1-4, max HP 8-16, flags]` (flags bit 0 = boss defeated). Encoded password is 6 characters.
- `GAME_OVER` and pause (Select during play) show `PASSWORD: XXXXXX`.
- `PASSWORD_ENTRY`: the 32-character alphabet laid out 8 x 4 on screen; D-pad moves a cursor (`>` character), A adds, B deletes, Start submits. A wrong password shows `WRONG PASSWORD` for 60 frames.

## 5. Text (title, ending)

- Title rows 9, 13, 15: `TEN YEARS' VOW`, `PRESS START`, `SELECT: PASSWORD`.
- Ending (screen 0 reused): `THE DEMON FALLS.` / `TEN YEARS LATER,` / `THE VOW IS KEPT.` / `THANK YOU FOR PLAYING`.
- No third-party names or trademarks anywhere in the game text.

## 6. Done when

- `chrono build samples/ten_years_vow/manifest.json` produces `build/ten_years_vow.nes` with no warnings.
- It plays start to ending in `web/index.html` (tinynes).
- One automated smoke test: build the ROM, run 120 frames with Start pressed at frame 10, check that the screen changed from the title (screen 0) to room 1 (compare a few known background pixels).
- PRG stays within 32 KB.
