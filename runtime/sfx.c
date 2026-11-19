/* sfx.c - sound effects on pulse 1, pulse 2 and noise.
 * Writes only $4000-$4007 and $400C-$400F ($4015 is written once by crt0).
 */
#include "chrono.h"

#define APU(a) (*(volatile unsigned char*)(a))

#define SQ1_VOL   0x4000
#define SQ1_SWEEP 0x4001
#define SQ1_LO    0x4002
#define SQ1_HI    0x4003
#define SQ2_VOL   0x4004
#define SQ2_SWEEP 0x4005
#define SQ2_LO    0x4006
#define SQ2_HI    0x4007
#define NOISE_VOL 0x400C
#define NOISE_LO  0x400E
#define NOISE_HI  0x400F

/* Frames until the second note of SFX_ITEM; 0 = idle (no APU writes). */
static unsigned char sfx_timer;

void sfx(unsigned char id)
{
    switch (id) {
    case SFX_JUMP:
        APU(SQ1_VOL)   = 0x9F;
        APU(SQ1_SWEEP) = 0xAB;
        APU(SQ1_LO)    = 0xA0;
        APU(SQ1_HI)    = 0x10;
        break;
    case SFX_HIT:
        APU(NOISE_VOL) = 0x1F;
        APU(NOISE_LO)  = 0x07;
        APU(NOISE_HI)  = 0x28;
        break;
    case SFX_SELECT:
        APU(SQ2_VOL)   = 0x97;
        APU(SQ2_SWEEP) = 0x00;
        APU(SQ2_LO)    = 0x7F;
        APU(SQ2_HI)    = 0x38;
        break;
    case SFX_ITEM:
        APU(SQ2_VOL)   = 0x9F;
        APU(SQ2_SWEEP) = 0x00;
        APU(SQ2_LO)    = 0x7F;
        APU(SQ2_HI)    = 0x48;
        sfx_timer = 5;
        break;
    default:
        break;
    }
}

void sfx_update(void)
{
    if (sfx_timer != 0) {
        --sfx_timer;
        if (sfx_timer == 0) {
            APU(SQ2_LO) = 0x54;
            APU(SQ2_HI) = 0x48;
        }
    }
}
