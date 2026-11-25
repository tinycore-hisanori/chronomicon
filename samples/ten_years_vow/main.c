/*
 * TEN YEARS' VOW - demo game for Chronomicon.
 *
 * Ten years ago a demon took the castle. The princess who escaped has trained as
 * a knight and comes back to keep her vow. Four rooms, one boss, a password.
 *
 * Controls: Left/Right walk, A jump, B sword, Select pause (shows the password),
 * Start begin / continue.
 *
 * Game code written with Claude against the Chronomicon runtime API (chrono.h).
 * Screens: 0 = title (reused for password entry, game over and ending),
 *          1..4 = castle rooms.
 */
#include "chrono.h"

/* ------------------------------------------------------------------ constants */
#define ST_TITLE     0
#define ST_PWENTRY   1
#define ST_PLAY      2
#define ST_PAUSE     3
#define ST_GAMEOVER  4
#define ST_ENDING    5

#define FLOOR_Y      176          /* sprite y of a 32-px sprite on the floor */
#define HP_MAX       8
#define JUMP_V       (-96)        /* 1/16 px per frame: -6.0 px/frame */
#define GRAVITY      4            /* +0.25 px/frame^2 */
#define FALL_MAX     96
#define ATTACK_LEN   12
#define INVULN_LEN   60

#define E_NONE       0
#define E_SKELETON   1
#define E_BAT        2
#define E_BOSS       3
#define MAX_ENEMIES  3

#define BOSS_HP      10

/* ------------------------------------------------------------------ state */
static unsigned char state, room, t, rnd;
static unsigned char px, facing, anim, attack, invuln, hp, hud_dirty, boss_dirty;
static int y16;                   /* player y in 1/16 px */
static int vy16;
static unsigned char on_ground;

static unsigned char e_type[MAX_ENEMIES], e_x[MAX_ENEMIES], e_y[MAX_ENEMIES];
static unsigned char e_hp[MAX_ENEMIES], e_dir[MAX_ENEMIES], e_hurt[MAX_ENEMIES];
static unsigned char e_lo[MAX_ENEMIES], e_hi[MAX_ENEMIES], e_hitby[MAX_ENEMIES];
static unsigned char attack_id;

static unsigned char fb_on, fb_x, fb_y, fb_dir;        /* boss fireball */
static unsigned char heart_on, heart_x, heart_y;       /* pickup */
static unsigned char boss_timer, boss_dead, end_timer;

static unsigned char save_room;                        /* checkpoint for passwords */
static char pw[PASSWORD_BUF_SIZE];
static unsigned char pw_state[3];

/* password entry */
static char entry[8];
static unsigned char entry_len, cursor, wrong_timer;
static const char alphabet[33] = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";

static char line[33];

/* platforms per room: {x0, x1, sprite_y} triples, ended by x1 = 0 */
static const unsigned char plat_room2[] = { 28, 84, 112,  108, 148, 80,  172, 228, 112,  0, 0, 0 };
static const unsigned char plat_room3[] = { 92, 116, 128,  140, 164, 96,  0, 0, 0 };
static const unsigned char plat_none[]  = { 0, 0, 0 };

/* ------------------------------------------------------------------ helpers */
static unsigned char random8(void) {
    rnd = (unsigned char)((rnd << 1) ^ ((rnd & 0x80) ? 0x1D : 0));
    if (rnd == 0) rnd = 0x5A;
    return rnd;
}

static unsigned char py(void) { return (unsigned char)(y16 >> 4); }

static const unsigned char *platforms(void) {
    if (room == 2) return plat_room2;
    if (room == 3) return plat_room3;
    return plat_none;
}

/* Show one line and give the VRAM queue a frame to drain (screen changes only). */
static void say(unsigned char col, unsigned char row, const char *s) {
    text(col, row, s);
    wait_frame();
}

static void fill_line(char c, unsigned char n) {
    unsigned char i;
    for (i = 0; i < n; ++i) line[i] = c;
    line[n] = 0;
}

static void bar(unsigned char start, unsigned char value, unsigned char max) {
    unsigned char i;
    for (i = 0; i < max; ++i) line[start + i] = (i < value) ? '=' : '-';
    line[start + max] = 0;
}

/* ------------------------------------------------------------------ HUD */
static void draw_hud(void) {
    /* "VOW-1  HP:========" */
    line[0] = 'V'; line[1] = 'O'; line[2] = 'W'; line[3] = '-'; line[4] = '0' + room;
    line[5] = ' '; line[6] = ' '; line[7] = 'H'; line[8] = 'P'; line[9] = ':';
    bar(10, hp, HP_MAX);
    text(2, 1, line);
    hud_dirty = 0;
}

static void draw_boss_hud(void) {
    unsigned char b = 0, i;
    for (i = 0; i < MAX_ENEMIES; ++i) if (e_type[i] == E_BOSS) b = e_hp[i];
    line[0] = 'D'; line[1] = 'E'; line[2] = 'M'; line[3] = 'O'; line[4] = 'N';
    line[5] = ' '; line[6] = ' '; line[7] = ' '; line[8] = ' '; line[9] = ':';
    bar(10, (unsigned char)((b + 1) >> 1), 8);
    text(2, 2, line);
    boss_dirty = 0;
}

static void clear_hud_line2(void) {
    fill_line(' ', 28);
    text(2, 2, line);
}

/* ------------------------------------------------------------------ password */
static void make_password(void) {
    pw_state[0] = save_room;
    pw_state[1] = HP_MAX;
    pw_state[2] = boss_dead;
    password_encode(pw_state, 3, pw);
}

/* ------------------------------------------------------------------ rooms */
static void add_enemy(unsigned char type, unsigned char x, unsigned char y,
                      unsigned char lo, unsigned char hi) {
    unsigned char i;
    for (i = 0; i < MAX_ENEMIES; ++i) {
        if (e_type[i] == E_NONE) {
            e_type[i] = type; e_x[i] = x; e_y[i] = y;
            e_lo[i] = lo; e_hi[i] = hi; e_dir[i] = 0; e_hurt[i] = 0; e_hitby[i] = 0;
            e_hp[i] = (type == E_SKELETON) ? 2 : (type == E_BAT) ? 1 : BOSS_HP;
            return;
        }
    }
}

static void enter_room(unsigned char r, unsigned char x) {
    unsigned char i;
    room = r;
    px = x;
    if (r > save_room) save_room = r;
    for (i = 0; i < MAX_ENEMIES; ++i) e_type[i] = E_NONE;
    fb_on = 0; heart_on = 0;
    load_screen(r);
    if (r == 1) add_enemy(E_SKELETON, 200, FLOOR_Y, 120, 220);
    if (r == 2) { add_enemy(E_SKELETON, 120, FLOOR_Y, 96, 200); add_enemy(E_BAT, 200, 96, 0, 0); }
    if (r == 3) { add_enemy(E_BAT, 96, 80, 0, 0); add_enemy(E_BAT, 176, 72, 0, 0); }
    if (r == 4 && !boss_dead) { add_enemy(E_BOSS, 184, FLOOR_Y, 120, 208); boss_timer = 60; }
    draw_hud();
    if (r == 4 && !boss_dead) draw_boss_hud();
}

static void start_play(unsigned char r) {
    hp = HP_MAX; invuln = 0; attack = 0; facing = 0;
    y16 = FLOOR_Y << 4; vy16 = 0; on_ground = 1;
    state = ST_PLAY;
    enter_room(r, (r == 1) ? 40 : 16);
}

/* ------------------------------------------------------------------ screens on 0 */
static void show_title(void) {
    state = ST_TITLE;
    load_screen(0);
    say(9, 9, "TEN YEARS' VOW");
    say(10, 13, "PRESS START");
    say(8, 15, "SELECT:PASSWORD");
}

static void draw_entry_row(void) {
    unsigned char i;
    for (i = 0; i < 6; ++i) line[i] = (i < entry_len) ? entry[i] : '_';
    line[6] = 0;
    text(13, 9, line);
}

static void draw_grid_row(unsigned char r) {
    unsigned char c, k = 0, idx;
    for (c = 0; c < 8; ++c) {
        idx = (unsigned char)(r * 8 + c);
        line[k++] = (idx == cursor) ? '>' : ' ';
        line[k++] = alphabet[idx];
    }
    line[k] = 0;
    text(8, (unsigned char)(11 + r), line);
}

static void show_pw_entry(void) {
    unsigned char r;
    state = ST_PWENTRY;
    entry_len = 0; cursor = 0; wrong_timer = 0;
    load_screen(0);
    say(11, 7, "PASSWORD");
    draw_entry_row(); wait_frame();
    for (r = 0; r < 4; ++r) { draw_grid_row(r); wait_frame(); }
    say(5, 16, "A:ADD B:DEL START:OK");
}

static void show_game_over(void) {
    unsigned char i;
    state = ST_GAMEOVER;
    make_password();
    load_screen(0);
    say(11, 9, "GAME OVER");
    line[0] = 'P'; line[1] = 'A'; line[2] = 'S'; line[3] = 'S'; line[4] = ':'; line[5] = ' ';
    for (i = 0; pw[i]; ++i) line[6 + i] = pw[i];
    line[6 + i] = 0;
    say(9, 12, line);
    say(7, 15, "START:CONTINUE");
}

static void show_ending(void) {
    state = ST_ENDING;
    load_screen(0);
    say(8, 7, "THE DEMON FALLS.");
    say(8, 9, "TEN YEARS LATER,");
    say(8, 11, "THE VOW IS KEPT.");
    say(5, 15, "THANK YOU FOR PLAYING");
}

/* ------------------------------------------------------------------ player */
static void hurt_player(unsigned char dmg, unsigned char from_x) {
    if (invuln || state != ST_PLAY) return;
    sfx(SFX_HIT);
    hp = (hp > dmg) ? (unsigned char)(hp - dmg) : 0;
    invuln = INVULN_LEN;
    if (from_x > px) { px = (px > 16) ? (unsigned char)(px - 16) : 0; }
    else { px = (px < 224) ? (unsigned char)(px + 16) : 240; }
    vy16 = -48; on_ground = 0;
    hud_dirty = 1;
}

static void update_player(void) {
    const unsigned char *p;
    unsigned char oldy, ny, feet;

    if (attack) --attack;
    else {
        if (btn(BTN_LEFT)) { if (px > 0) --px; facing = 1; ++anim; }
        else if (btn(BTN_RIGHT)) { if (px < 240) ++px; facing = 0; ++anim; }
        if (btnp(BTN_B)) { attack = ATTACK_LEN; ++attack_id; sfx(SFX_SELECT); }
    }
    if (btnp(BTN_A) && on_ground) { vy16 = JUMP_V; on_ground = 0; sfx(SFX_JUMP); }

    /* vertical movement */
    oldy = py();
    vy16 += GRAVITY;
    if (vy16 > FALL_MAX) vy16 = FALL_MAX;
    y16 += vy16;
    if (y16 < 0) y16 = 0;
    ny = py();
    on_ground = 0;
    if (ny >= FLOOR_Y) {
        y16 = FLOOR_Y << 4; vy16 = 0; on_ground = 1;
    } else if (vy16 >= 0) {
        feet = (unsigned char)(px + 8);
        for (p = platforms(); p[1]; p += 3) {
            if (feet >= p[0] && feet <= p[1] && oldy <= p[2] && ny >= p[2]) {
                y16 = (int)p[2] << 4; vy16 = 0; on_ground = 1;
            }
        }
    }

    /* spikes in room 3 */
    if (room == 3 && on_ground && py() == FLOOR_Y) {
        feet = (unsigned char)(px + 8);
        if (feet >= 80 && feet < 176) { hurt_player(2, (unsigned char)(px + 16)); vy16 = -72; }
    }

    if (invuln) --invuln;

    /* room edges */
    if (room == 1 && px < 24) px = 24;
    if (room == 4 && px > 216) px = 216;
    if (px >= 240 && room < 4) enter_room((unsigned char)(room + 1), 8);
    else if (px == 0 && room > 1) enter_room((unsigned char)(room - 1), 228);
}

static void draw_player(void) {
    const unsigned char *m;
    unsigned char y = py();
    if (invuln && (t & 4)) return;                     /* blink */
    if (attack) m = facing ? metasprite_knight_attack_flip : metasprite_knight_attack;
    else if (!on_ground) m = facing ? metasprite_knight_jump_flip : metasprite_knight_jump;
    else if (btn(BTN_LEFT) || btn(BTN_RIGHT))
        m = (anim & 8) ? (facing ? metasprite_knight_walk1_flip : metasprite_knight_walk1)
                       : (facing ? metasprite_knight_walk2_flip : metasprite_knight_walk2);
    else m = facing ? metasprite_knight_idle_flip : metasprite_knight_idle;
    meta_spr(px, y, m);
    if (attack > 2) {
        if (facing) { if (px >= 16) meta_spr((unsigned char)(px - 16), (unsigned char)(y + 12), metasprite_slash_flip); }
        else if (px < 224) meta_spr((unsigned char)(px + 16), (unsigned char)(y + 12), metasprite_slash);
    }
}

/* ------------------------------------------------------------------ collisions */
static unsigned char overlap(unsigned char ax, unsigned char ay, unsigned char aw, unsigned char ah,
                             unsigned char bx, unsigned char by, unsigned char bw, unsigned char bh) {
    return (unsigned char)(ax < (unsigned char)(bx + bw) && bx < (unsigned char)(ax + aw) &&
                           ay < (unsigned char)(by + bh) && by < (unsigned char)(ay + ah));
}

static unsigned char sword_hits(unsigned char x, unsigned char y, unsigned char w, unsigned char h) {
    unsigned char sx;
    if (attack < 3 || attack > 10) return 0;
    if (facing) { if (px < 16) return 0; sx = (unsigned char)(px - 16); }
    else { if (px > 224) return 0; sx = (unsigned char)(px + 16); }
    return overlap(sx, (unsigned char)(py() + 12), 16, 16, x, y, w, h);
}

/* ------------------------------------------------------------------ enemies */
static void defeat(unsigned char i) {
    sfx(SFX_HIT);
    if (e_type[i] == E_BOSS) {
        boss_dead = 1; fb_on = 0; end_timer = 90;
    } else if (!heart_on && (random8() % 3) == 0) {
        heart_on = 1; heart_x = (unsigned char)(e_x[i] + 4); heart_y = e_y[i];
    }
    e_type[i] = E_NONE;
}

static void update_enemy(unsigned char i) {
    unsigned char w = 16, h = 32, x, y;
    switch (e_type[i]) {
    case E_SKELETON:
        if (t & 1) {
            if (e_dir[i]) { if (++e_x[i] >= e_hi[i]) e_dir[i] = 0; }
            else { if (--e_x[i] <= e_lo[i]) e_dir[i] = 1; }
        }
        break;
    case E_BAT:
        h = 16;
        if (t & 1) { if (e_x[i] + 8 > px + 8) --e_x[i]; else ++e_x[i]; }
        if ((t & 3) == 0) {
            unsigned char target = (unsigned char)(py() + 4);
            if (e_y[i] < target) ++e_y[i]; else if (e_y[i] > target) --e_y[i];
        }
        if ((t & 31) < 16) { if (e_y[i] > 40) --e_y[i]; } else ++e_y[i];
        break;
    case E_BOSS:
        w = 32;
        if ((t & 3) == 0) {
            if (e_x[i] > px + 24 && e_x[i] > e_lo[i]) --e_x[i];
            else if (e_x[i] + 24 < px && e_x[i] < e_hi[i]) ++e_x[i];
        }
        if (boss_timer) --boss_timer;
        else if (!fb_on) {
            fb_on = 1; fb_y = (unsigned char)(e_y[i] + 12);
            fb_dir = (px < e_x[i]);
            fb_x = fb_dir ? e_x[i] : (unsigned char)(e_x[i] + 24);
            boss_timer = 110;
            sfx(SFX_JUMP);
        }
        break;
    }
    x = e_x[i]; y = e_y[i];

    /* sword */
    if (e_hurt[i]) --e_hurt[i];
    else if (e_hitby[i] != attack_id && sword_hits(x, y, w, h)) {
        e_hitby[i] = attack_id;
        e_hurt[i] = (e_type[i] == E_BOSS) ? 16 : 12;
        sfx(SFX_HIT);
        if (--e_hp[i] == 0) { defeat(i); if (room == 4) boss_dirty = 1; return; }
        if (e_type[i] == E_BOSS) {
            boss_dirty = 1;   /* stagger back so the player is not pinned */
            if (px < x) { if (e_x[i] < e_hi[i]) e_x[i] = (unsigned char)(x + 8); }
            else if (e_x[i] > e_lo[i]) e_x[i] = (unsigned char)(x - 8);
        }
        else e_x[i] = facing ? (unsigned char)(x - 8) : (unsigned char)(x + 8);
    }

    /* touch */
    if (overlap((unsigned char)(px + 4), (unsigned char)(py() + 4), 8, 28,
                (unsigned char)(x + 2), (unsigned char)(y + 2), (unsigned char)(w - 4), (unsigned char)(h - 4)))
        hurt_player(1, (unsigned char)(x + (w >> 1)));
}

static void draw_enemy(unsigned char i) {
    unsigned char x = e_x[i], y = e_y[i];
    unsigned char left = (x + 8 > px + 8);   /* faces the player when chasing */
    if (e_hurt[i] && (t & 2)) return;
    switch (e_type[i]) {
    case E_SKELETON:
        meta_spr(x, y, (t & 16) ? (e_dir[i] ? metasprite_skeleton_a : metasprite_skeleton_a_flip)
                                : (e_dir[i] ? metasprite_skeleton_b : metasprite_skeleton_b_flip));
        break;
    case E_BAT:
        meta_spr(x, y, (t & 8) ? metasprite_bat_a : metasprite_bat_b);
        break;
    case E_BOSS:
        meta_spr(x, y, (t & 32) ? (left ? metasprite_demon_a_flip : metasprite_demon_a)
                                : (left ? metasprite_demon_b_flip : metasprite_demon_b));
        break;
    }
}

static void update_extras(void) {
    if (fb_on) {
        if (fb_dir) { if (fb_x < 3) fb_on = 0; else fb_x -= 2; }
        else { if (fb_x > 244) fb_on = 0; else fb_x += 2; }
        if (fb_on && overlap((unsigned char)(px + 4), (unsigned char)(py() + 4), 8, 28, fb_x, fb_y, 8, 12))
            { hurt_player(1, fb_x); fb_on = 0; }
    }
    if (heart_on) {
        if (heart_y < FLOOR_Y + 16) ++heart_y;
        if (overlap(px, py(), 16, 32, heart_x, heart_y, 8, 16)) {
            heart_on = 0; sfx(SFX_ITEM);
            hp = (hp + 2 > HP_MAX) ? HP_MAX : (unsigned char)(hp + 2);
            hud_dirty = 1;
        }
    }
}

static void draw_extras(void) {
    if (fb_on) meta_spr(fb_x, fb_y, fb_dir ? metasprite_fireball_flip : metasprite_fireball);
    if (heart_on) meta_spr(heart_x, heart_y, metasprite_heart);
}

/* ------------------------------------------------------------------ states */
static void play_frame(void) {
    unsigned char i;
    if (btnp(BTN_SELECT)) {
        state = ST_PAUSE;
        make_password();
        line[0] = 'P'; line[1] = 'A'; line[2] = 'U'; line[3] = 'S'; line[4] = 'E';
        line[5] = ' '; line[6] = ' ';
        for (i = 0; pw[i]; ++i) line[7 + i] = pw[i];
        line[7 + i] = ' '; line[8 + i] = ' '; line[9 + i] = 0;
        text(2, 2, line);
        return;
    }
    update_player();
    if (state != ST_PLAY) return;
    for (i = 0; i < MAX_ENEMIES; ++i) if (e_type[i]) update_enemy(i);
    update_extras();

    /* draw: alternate the order so that 9-sprite lines flicker instead of losing one sprite */
    if (t & 1) {
        draw_player();
        for (i = 0; i < MAX_ENEMIES; ++i) if (e_type[i]) draw_enemy(i);
        draw_extras();
    } else {
        draw_extras();
        for (i = MAX_ENEMIES; i-- > 0;) if (e_type[i]) draw_enemy(i);
        draw_player();
    }

    if (hud_dirty) draw_hud();
    else if (boss_dirty) draw_boss_hud();

    if (hp == 0) { show_game_over(); return; }
    if (boss_dead && end_timer) {
        if (--end_timer == 0) show_ending();
    }
}

static void pw_frame(void) {
    unsigned char old = cursor, r;
    if (wrong_timer) {
        if (--wrong_timer == 0) say(9, 18, "              ");
        return;
    }
    if (btnp(BTN_LEFT))  cursor = (unsigned char)((cursor & 0x18) | ((cursor - 1) & 7));
    if (btnp(BTN_RIGHT)) cursor = (unsigned char)((cursor & 0x18) | ((cursor + 1) & 7));
    if (btnp(BTN_UP))    cursor = (unsigned char)((cursor - 8) & 31);
    if (btnp(BTN_DOWN))  cursor = (unsigned char)((cursor + 8) & 31);
    if (cursor != old) {
        sfx(SFX_SELECT);
        draw_grid_row((unsigned char)(old >> 3));
        if ((old >> 3) != (cursor >> 3)) draw_grid_row((unsigned char)(cursor >> 3));
        return;
    }
    if (btnp(BTN_A) && entry_len < 6) { entry[entry_len++] = alphabet[cursor]; sfx(SFX_SELECT); draw_entry_row(); }
    else if (btnp(BTN_B) && entry_len) { --entry_len; draw_entry_row(); }
    else if (btnp(BTN_START)) {
        r = 0;
        entry[6] = 0;   /* decode wants a NUL-terminated string; len is the state size */
        if (entry_len == 6 && password_decode(entry, 3, pw_state) &&
            pw_state[0] >= 1 && pw_state[0] <= 4 && pw_state[2] <= 1) r = pw_state[0];
        if (r) {
            sfx(SFX_ITEM);
            save_room = r; boss_dead = 0;
            start_play(r);
        } else {
            sfx(SFX_HIT);
            text(9, 18, "WRONG PASSWORD");
            wrong_timer = 60;
        }
    }
}

void main(void) {
    rnd = 0x5A;
    show_title();
    for (;;) {
        wait_frame();
        pad_update();
        ++t;
        oam_clear();
        switch (state) {
        case ST_TITLE:
            random8();
            if (btnp(BTN_START)) { sfx(SFX_SELECT); save_room = 1; boss_dead = 0; start_play(1); }
            else if (btnp(BTN_SELECT)) { sfx(SFX_SELECT); show_pw_entry(); }
            break;
        case ST_PWENTRY:
            pw_frame();
            break;
        case ST_PLAY:
            play_frame();
            break;
        case ST_PAUSE:
            draw_player();
            if (btnp(BTN_SELECT) || btnp(BTN_START)) {
                state = ST_PLAY;
                if (room == 4 && !boss_dead) draw_boss_hud(); else clear_hud_line2();
            }
            break;
        case ST_GAMEOVER:
            if (btnp(BTN_START)) { sfx(SFX_SELECT); start_play(save_room); }
            break;
        case ST_ENDING:
            if (btnp(BTN_START)) show_title();
            break;
        }
    }
}
