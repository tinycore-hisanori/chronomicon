/* oam.c - OAM shadow buffer and metasprite placement. */
#include "chrono.h"

/* The shadow lives in segment OAM ($0200-$02FF); crt0 and the NMI DMA use it as _oam. */
#pragma bss-name (push, "OAM")
unsigned char oam[256];
#pragma bss-name (pop)

unsigned char oam_count;              /* number of hardware sprites used this frame */

void oam_clear(void)
{
    unsigned char i;

    for (i = 0; i < 64; ++i) {
        oam[(unsigned char)(i << 2)] = 0xFF;   /* Y = $FF hides the sprite */
    }
    oam_count = 0;
}

/* Metasprite data: groups of 4 bytes (dx, dy, tile, attr) ended by a single byte 128. */
void meta_spr(unsigned char x, unsigned char y, const unsigned char *meta)
{
    const unsigned char *p;
    unsigned char n, o;

    n = 0;
    p = meta;
    while (*p != 128) {
        ++n;
        p += 4;
        if (n > 64) {                  /* cannot fit anyway; also bounds the scan */
            return;
        }
    }
    if ((unsigned char)(oam_count + n) > 64 || n == 0) {
        return;
    }

    o = (unsigned char)(oam_count << 2);
    p = meta;
    while (n != 0) {
        oam[o]                      = (unsigned char)(y + p[1] - 1);
        oam[(unsigned char)(o + 1)] = p[2];
        oam[(unsigned char)(o + 2)] = p[3];
        oam[(unsigned char)(o + 3)] = (unsigned char)(x + p[0]);
        o = (unsigned char)(o + 4);
        p += 4;
        --n;
        ++oam_count;
    }
}
