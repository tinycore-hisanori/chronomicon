/* runtime.c - frame synchronisation. */
#include "chrono.h"
#include "chrono_zp.h"

void sfx_update(void);                    /* defined in sfx.c */

/* Number of text() writes dropped because the VRAM queue was full (used by text.c). */
unsigned char vq_dropped;

void wait_frame(void)
{
    vram_ready = 1;                       /* allow NMI to flush the VRAM queue */
    frame_flag = 0;
    while (!frame_flag) {
        /* spin until the NMI handler sets frame_flag */
    }
    sfx_update();
}
