/* text.c - VRAM update queue producer and text(). */
#include "chrono.h"
#include "chrono_zp.h"

/* Queue entries: [len][addr_hi][addr_lo][payload...], consumed by nmi.s as _vq_buf. */
unsigned char vq_buf[128];

extern unsigned char vq_dropped;

void vramq_push(unsigned int addr, const unsigned char *src, unsigned char len)
{
    unsigned char t, i;

    if (len == 0 || len > 32) return;
    t = vq_tail;
    if ((unsigned char)(128 - t) < (unsigned char)(len + 3)) return;
    vq_buf[t] = len;
    vq_buf[(unsigned char)(t + 1)] = (unsigned char)(addr >> 8);
    vq_buf[(unsigned char)(t + 2)] = (unsigned char)addr;
    t += 3;
    for (i = 0; i < len; ++i) {
        vq_buf[t] = src[i];
        ++t;
    }
    vq_tail = t;
}

static unsigned char text_len(const char *s, unsigned char max)
{
    unsigned char n;

    n = 0;
    while (n < max && s[n] != 0) ++n;
    return n;
}

void text(unsigned char col, unsigned char row, const char *s)
{
    unsigned int pos, room, addr;
    unsigned char n, left, chunk, need_chunks;
    unsigned int need;
    const unsigned char *p;

    if (col >= 32 || row >= 30) return;
    pos = ((unsigned int)row << 5) + col;
    room = 960 - pos;                       /* tiles left up to $23BF */
    n = text_len(s, 255);
    if (n == 0) return;
    if ((unsigned int)n > room) n = (unsigned char)room;

    need_chunks = (unsigned char)((n + 31) >> 5);
    need = (unsigned int)n + 3u * need_chunks;
    if (need > (unsigned int)(128 - vq_tail)) {
        ++vq_dropped;
        return;
    }

    addr = 0x2000 + pos;
    p = (const unsigned char *)s;
    left = n;
    while (left != 0) {
        chunk = left > 32 ? 32 : left;
        vramq_push(addr, p, chunk);
        addr += chunk;
        p += chunk;
        left -= chunk;
    }
}
