/* Mailbox ROM for the runtime tests (one command per run, results read back by the driver).
 * Addresses are found through the ld65 label file. */
#include "chrono.h"
#include "chrono_zp.h"

extern unsigned char vq_buf[];       /* defined in runtime/text.c */

unsigned char rt_cmd;                /* driver writes; ROM clears it and increments rt_done */
unsigned char rt_done;
unsigned char rt_arg[32];            /* command arguments */
unsigned char rt_meta[96];           /* metasprite blob(s) in RAM */
unsigned char rt_str[128];           /* NUL-terminated string */
unsigned char rt_dump[130];          /* rt_dump[0] = vq_tail, then vq_buf[0..tail) */
unsigned char cnt_held;              /* frames with btn(BTN_A) */
unsigned char cnt_edge;              /* frames with btnp(BTN_A) */

#define CMD_META        1   /* rt_arg[0] = calls, then (x, y, offset into rt_meta) per call */
#define CMD_TEXT        2   /* rt_arg[0] = col, rt_arg[1] = row, string in rt_str */
#define CMD_TEXT_DUMP   3   /* like TEXT, then copy the queue into rt_dump */
#define CMD_LOAD_SCREEN 4   /* rt_arg[0] = n */

void main(void) {
    unsigned char i, n, cmd;
    for (;;) {
        wait_frame();
        pad_update();
        if (btn(BTN_A)) ++cnt_held;
        if (btnp(BTN_A)) ++cnt_edge;

        cmd = rt_cmd;
        if (cmd == 0) continue;
        if (cmd == CMD_META) {
            oam_clear();
            n = rt_arg[0];
            for (i = 0; i < n && i < 10; ++i) {
                meta_spr(rt_arg[1 + 3 * i], rt_arg[2 + 3 * i], rt_meta + rt_arg[3 + 3 * i]);
            }
        } else if (cmd == CMD_TEXT || cmd == CMD_TEXT_DUMP) {
            text(rt_arg[0], rt_arg[1], (const char *)rt_str);
            if (cmd == CMD_TEXT_DUMP) {
                /* The NMI only drains the queue after the next wait_frame(), so this copy is stable. */
                n = vq_tail;
                rt_dump[0] = n;
                for (i = 0; i < n && i < 128; ++i) rt_dump[1 + i] = vq_buf[i];
            }
        } else if (cmd == CMD_LOAD_SCREEN) {
            load_screen(rt_arg[0]);
        }
        rt_cmd = 0;
        ++rt_done;
    }
}
