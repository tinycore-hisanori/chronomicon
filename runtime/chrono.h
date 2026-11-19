/* chrono.h - public interface of the Chronomicon runtime (game code includes only this). */
#ifndef CHRONO_H
#define CHRONO_H
#include "assets_decl.h"                  /* palette_*, metasprite_* (generated) */

/* Buttons: bit i = i-th serial read of controller 1 (same bits as tinynes). */
#define BTN_A      0x01
#define BTN_B      0x02
#define BTN_SELECT 0x04
#define BTN_START  0x08
#define BTN_UP     0x10
#define BTN_DOWN   0x20
#define BTN_LEFT   0x40
#define BTN_RIGHT  0x80

/* Written only by pad_update(); both are 0 before the first call (BSS is cleared). */
extern unsigned char pad_now;             /* held, from the last pad_update()   */
extern unsigned char pad_pressed;         /* now & ~prev, from the last pad_update() */
#define btn(b)  ((pad_now & (b)) != 0)    /* 1 while held, else 0 */
#define btnp(b) ((pad_pressed & (b)) != 0) /* 1 on the frame of the press, else 0 */

void wait_frame(void);
void pad_update(void);
void oam_clear(void);
void meta_spr(unsigned char x, unsigned char y, const unsigned char *meta);
void text(unsigned char col, unsigned char row, const char *s);
void __fastcall__ load_screen(unsigned char n);
/* Defined in the generated screens.s as _screen_count (cc65 adds the underscore). */
extern const unsigned char screen_count;

#define SFX_JUMP   0
#define SFX_HIT    1
#define SFX_SELECT 2
#define SFX_ITEM   3
void sfx(unsigned char id);

/* Maximum number of state bytes password_encode() accepts. */
#define PASSWORD_MAX_STATE_LEN 8
/* Size of the output buffer for password_encode(): 14 characters + NUL for len = 8. */
#define PASSWORD_BUF_SIZE      15
void password_encode(const unsigned char *state, unsigned char len, char *out);
unsigned char password_decode(const char *in, unsigned char len, unsigned char *state);
#endif
