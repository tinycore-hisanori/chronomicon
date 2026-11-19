"""Python oracle for ``runtime/password.c`` (Requirement 12).

Bits are packed MSB first, 5 bits per symbol; the last symbol is the sum of the
data symbols modulo 32. Missing bits in the final data symbol are zero on
encode and ignored on decode.
"""

from __future__ import annotations

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
MAX_STATE_LEN = 8


def data_len(n: int) -> int:
    """Number of data symbols for ``n`` state bytes: ceil(8 * n / 5)."""
    return (8 * n + 4) // 5


def encode(state: bytes) -> str:
    """Encode ``state`` (1..8 bytes). Any other length gives an empty string."""
    n = len(state)
    if n < 1 or n > MAX_STATE_LEN:
        return ""
    total = 8 * n
    syms = []
    for i in range(data_len(n)):
        val = 0
        for k in range(5):
            pos = i * 5 + k
            val <<= 1
            if pos < total:
                val |= (state[pos >> 3] >> (7 - (pos & 7))) & 1
        syms.append(val)
    check = sum(syms) & 31
    return "".join(ALPHABET[v] for v in syms + [check])


def decode(pw: str, n: int) -> bytes | None:
    """Decode ``pw`` into ``n`` bytes, or return None when it is invalid.

    Step order matches the C code: length range, string length, alphabet,
    checksum, rebuild.
    """
    if n < 1 or n > MAX_STATE_LEN:
        return None
    d = data_len(n)
    if len(pw) != d + 1:
        return None
    vals = []
    for c in pw:
        v = ALPHABET.find(c)
        if v < 0:
            return None
        vals.append(v)
    if (sum(vals[:d]) & 31) != vals[d]:
        return None
    out = bytearray(n)
    total = 8 * n
    for i in range(d):
        for k in range(5):
            pos = i * 5 + k
            if pos < total and (vals[i] >> (4 - k)) & 1:
                out[pos >> 3] |= 0x80 >> (pos & 7)
    return bytes(out)
