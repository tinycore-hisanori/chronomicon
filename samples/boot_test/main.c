/* Boot_Test sample: a sprite that jumps 16 pixels to the right on every START press. */
#include "chrono.h"

void main(void) {
    unsigned char px = 64;
    for (;;) {
        wait_frame();
        pad_update();
        if (btnp(BTN_START)) px += 16;
        oam_clear();
        meta_spr(px, 120, metasprite_player);
    }
}
