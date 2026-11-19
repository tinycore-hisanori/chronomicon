/* pad.c - controller 1 polling. */
#include "chrono.h"

#define JOY1 (*(volatile unsigned char*)0x4016)

unsigned char pad_now;
unsigned char pad_pressed;
static unsigned char pad_prev;

void pad_update(void)
{
    unsigned char i;
    unsigned char now;

    now = 0;
    JOY1 = 1;                             /* strobe high, then low to latch buttons */
    JOY1 = 0;
    for (i = 0; i < 8; ++i) {
        now |= (unsigned char)((JOY1 & 1) << i);   /* A first, in bit 0 */
    }
    pad_pressed = now & (unsigned char)~pad_prev;
    pad_prev = now;
    pad_now = now;
}
