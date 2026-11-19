/* TEN YEARS' VOW - art walk-through preview (not the game).
 * Lets you walk the knight through the four rooms to check the converted art on
 * the real runtime. Written by Claude as a test harness; the real game is
 * samples/ten_years_vow/main.c.
 * Controls: Start = begin, Left/Right = walk, A = jump, B = sword.
 */
#include "chrono.h"

#define FLOOR_Y 176

static unsigned char state;          /* 0 title, 1 play */
static unsigned char room;           /* 1..4 = screen number */
static unsigned char px, facing, anim, attack;
static int y4;                       /* player y in 1/4 px */
static signed char vy4;              /* vertical speed in 1/4 px per frame */
static unsigned char on_ground;
static unsigned char t;              /* frame counter */
static unsigned char ex, edir, ealive; /* one walking enemy per room */
static unsigned char bx, by, balive;   /* one bat per room */

/* platforms per room: {x0, x1, top_y_of_sprite} ; 0-terminated by x1 = 0 */
static const unsigned char plat2[] = { 32, 80, 112, 112, 144, 80, 176, 224, 112, 0, 0, 0 };
static const unsigned char plat3[] = { 96, 112, 128, 144, 160, 96, 0, 0, 0 };

static const unsigned char *plats(void) {
    if (room == 2) return plat2;
    if (room == 3) return plat3;
    return 0;
}

static void hud(void) {
    static char line[] = "ROOM 1  ART PREVIEW";
    line[5] = '0' + room;
    text(2, 1, line);
    text(2, 2, "A JUMP  B SWORD     ");
}

static void enter_room(unsigned char r) {
    room = r;
    load_screen(r);
    hud();
    ealive = (r == 1 || r == 2 || r == 4);
    ex = 200; edir = 0;
    balive = (r == 2 || r == 3);
    bx = 180; by = 80;
}

static void title(void) {
    text(9, 9, "TEN YEARS' VOW");
    text(10, 13, "PRESS START");
    text(7, 15, "(ART PREVIEW ROM)");
}

static void update_player(void) {
    const unsigned char *p;
    unsigned char feet, newy;
    if (attack) {
        --attack;
    } else {
        if (btn(BTN_LEFT) && px > 2) { px -= 1; facing = 1; ++anim; }
        else if (btn(BTN_RIGHT)) { px += 1; facing = 0; ++anim; }
        if (btnp(BTN_B)) { attack = 12; sfx(SFX_SELECT); }
    }
    if (btnp(BTN_A) && on_ground) { vy4 = -18; on_ground = 0; sfx(SFX_JUMP); }

    /* gravity */
    if (vy4 < 16) ++vy4;
    y4 += vy4;
    newy = (unsigned char)(y4 >> 2);
    on_ground = 0;
    if (newy >= FLOOR_Y) { y4 = FLOOR_Y << 2; vy4 = 0; on_ground = 1; }
    else if (vy4 >= 0) {
        p = plats();
        if (p) {
            while (p[1]) {
                feet = (unsigned char)(px + 8);
                if (feet >= p[0] && feet <= p[1] && newy >= p[2] && newy <= p[2] + 6) {
                    y4 = p[2] << 2; vy4 = 0; on_ground = 1;
                }
                p += 3;
            }
        }
    }

    /* room edges */
    if (px >= 240 && room < 4) { enter_room(room + 1); px = 8; }
    else if (px <= 2 && room > 1) { enter_room(room - 1); px = 230; }
}

static void draw_player(void) {
    const unsigned char *m;
    unsigned char y = (unsigned char)(y4 >> 2);
    if (attack) m = facing ? metasprite_knight_attack_flip : metasprite_knight_attack;
    else if (!on_ground) m = facing ? metasprite_knight_jump_flip : metasprite_knight_jump;
    else if (btn(BTN_LEFT) || btn(BTN_RIGHT))
        m = (anim & 8) ? (facing ? metasprite_knight_walk1_flip : metasprite_knight_walk1)
                       : (facing ? metasprite_knight_walk2_flip : metasprite_knight_walk2);
    else m = facing ? metasprite_knight_idle_flip : metasprite_knight_idle;
    meta_spr(px, y, m);
    if (attack > 2) {
        if (facing) meta_spr(px - 16, y + 12, metasprite_slash_flip);
        else meta_spr(px + 16, y + 12, metasprite_slash);
    }
}

static unsigned char hit(unsigned char x, unsigned char w) {
    unsigned char sx = facing ? px - 16 : px + 16;
    if (!attack) return 0;
    return (unsigned char)(sx + 16 > x && sx < x + w);
}

static void update_enemies(void) {
    if (ealive && room != 4) {
        if (t & 1) { if (edir) { if (++ex > 220) edir = 0; } else { if (--ex < 120) edir = 1; } }
        meta_spr(ex, FLOOR_Y, (t & 16) ? (edir ? metasprite_skeleton_a : metasprite_skeleton_a_flip)
                                       : (edir ? metasprite_skeleton_b : metasprite_skeleton_b_flip));
        if (hit(ex, 16) && (unsigned char)(y4 >> 2) > 140) { ealive = 0; sfx(SFX_HIT); }
    }
    if (ealive && room == 4) {
        meta_spr(176, 144, (t & 32) ? metasprite_demon_a_flip : metasprite_demon_b_flip);
        if ((t & 63) < 40) meta_spr((unsigned char)(168 - ((t & 63) << 1)), 156, metasprite_fireball);
    }
    if (balive) {
        if (t & 1) { if (bx > px + 8) --bx; else ++bx; }
        by = (unsigned char)(70 + ((t & 32) ? (t & 31) : (31 - (t & 31))));
        meta_spr(bx, by, (t & 8) ? metasprite_bat_a : metasprite_bat_b);
        if (hit(bx, 16) && (unsigned char)(y4 >> 2) < by + 32) { balive = 0; sfx(SFX_ITEM); }
    }
}

void main(void) {
    title();
    for (;;) {
        wait_frame();
        pad_update();
        ++t;
        oam_clear();
        if (state == 0) {
            if (btnp(BTN_START)) {
                state = 1; px = 40; y4 = FLOOR_Y << 2; on_ground = 1;
                sfx(SFX_SELECT);
                enter_room(1);
            }
            continue;
        }
        update_player();
        draw_player();
        update_enemies();
    }
}
