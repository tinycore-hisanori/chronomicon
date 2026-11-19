/* Mailbox ROM for the password tests. The test driver fills pw_cases and pw_count,
 * sets pw_ctrl = 1, and waits until the ROM sets pw_ctrl = 2. Addresses are found
 * through the ld65 label file (_pw_cases, _pw_count, _pw_ctrl). */
#include "chrono.h"

#define PW_CASES 16

struct pw_case {            /* 32 bytes: op 0, len 1, state 2..9, pw 10..25, result 26 */
    unsigned char op;       /* 0 = idle, 1 = encode, 2 = decode */
    unsigned char len;
    unsigned char state[8];
    char          pw[16];
    unsigned char result;   /* decode return value */
    unsigned char pad[5];
};

struct pw_case pw_cases[PW_CASES];
unsigned char pw_count;
unsigned char pw_ctrl;      /* driver sets 1; ROM sets 2 when every case is done */

void main(void) {
    unsigned char i;
    struct pw_case *c;
    for (;;) {
        wait_frame();
        pad_update();
        if (pw_ctrl == 1) {
            for (i = 0; i < pw_count && i < PW_CASES; ++i) {
                c = &pw_cases[i];
                if (c->op == 1) {
                    password_encode(c->state, c->len, c->pw);
                } else if (c->op == 2) {
                    c->result = password_decode(c->pw, c->len, c->state);
                }
            }
            pw_ctrl = 2;
        }
    }
}
