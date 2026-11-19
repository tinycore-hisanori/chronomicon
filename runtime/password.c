/* password.c - password encode/decode (5 bits per symbol, mod-32 checksum). */
#include "chrono.h"

static const char pw_alphabet[32] = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";

/* Number of data symbols for len bytes: ceil(8*len / 5). */
static unsigned char pw_data_len(unsigned char len)
{
    return (unsigned char)((unsigned char)(len << 3) + 4) / 5;
}

/* Value 0..31 of an alphabet character, or 0xFF when it is not in the alphabet. */
static unsigned char pw_value(char c)
{
    unsigned char i;

    for (i = 0; i < 32; ++i) {
        if (pw_alphabet[i] == c) {
            return i;
        }
    }
    return 0xFF;
}

void password_encode(const unsigned char *state, unsigned char len, char *out)
{
    unsigned char d;
    unsigned char i;
    unsigned char k;
    unsigned char pos;
    unsigned char total;
    unsigned char val;
    unsigned char sum;

    if (len == 0 || len > PASSWORD_MAX_STATE_LEN) {
        out[0] = 0;
        return;
    }
    d = pw_data_len(len);
    total = (unsigned char)(len << 3);
    sum = 0;
    for (i = 0; i < d; ++i) {
        val = 0;
        for (k = 0; k < 5; ++k) {
            pos = (unsigned char)(i * 5 + k);
            val = (unsigned char)(val << 1);
            if (pos < total) {
                val |= (unsigned char)((state[pos >> 3] >> (7 - (pos & 7))) & 1);
            }
        }
        sum = (unsigned char)(sum + val);
        out[i] = pw_alphabet[val];
    }
    out[d] = pw_alphabet[sum & 31];
    out[d + 1] = 0;
}

unsigned char password_decode(const char *in, unsigned char len, unsigned char *state)
{
    unsigned char tmp[8];
    unsigned char vals[14];
    unsigned char d;
    unsigned char n;
    unsigned char count;
    unsigned char i;
    unsigned char k;
    unsigned char pos;
    unsigned char total;
    unsigned char v;
    unsigned char sum;

    if (len == 0 || len > PASSWORD_MAX_STATE_LEN) {
        return 0;
    }
    d = pw_data_len(len);
    n = (unsigned char)(d + 1);

    count = 0;
    while (count <= n && in[count] != 0) {
        ++count;
    }
    if (count != n) {
        return 0;
    }

    for (i = 0; i < n; ++i) {
        v = pw_value(in[i]);
        if (v == 0xFF) {
            return 0;
        }
        vals[i] = v;
    }

    sum = 0;
    for (i = 0; i < d; ++i) {
        sum = (unsigned char)(sum + vals[i]);
    }
    if ((unsigned char)(sum & 31) != vals[d]) {
        return 0;
    }

    for (i = 0; i < 8; ++i) {
        tmp[i] = 0;
    }
    total = (unsigned char)(len << 3);
    for (i = 0; i < d; ++i) {
        for (k = 0; k < 5; ++k) {
            pos = (unsigned char)(i * 5 + k);
            if (pos < total && ((vals[i] >> (4 - k)) & 1)) {
                tmp[pos >> 3] |= (unsigned char)(0x80 >> (pos & 7));
            }
        }
    }
    for (i = 0; i < len; ++i) {
        state[i] = tmp[i];
    }
    return 1;
}
