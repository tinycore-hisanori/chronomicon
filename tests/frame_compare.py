"""Frame comparison helpers for the ROM-vs-reference fidelity tests.

Frames are 256x240 palette-index buffers in row-major order (tinynes ``indexBuffer`` or the
asset converter's ``render_nes_frame``). A mask is a ``bytearray`` of the same size where a
non-zero entry means "ignore this pixel".
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Sequence

WIDTH = 256
HEIGHT = 240
FRAME_SIZE = WIDTH * HEIGHT
SPRITE_COUNT = 64
SPRITE_HEIGHT = 16  # 8x16 sprite mode
SPRITE_WIDTH = 8


def sprite_mask(oam_bytes: Sequence[int]) -> bytearray:
    """Mask covering all 64 OAM entries (8x16 mode).

    Entry ``i`` is (Y, tile, attr, X) at ``oam_bytes[4*i:4*i+4]``. It covers columns
    ``X..X+7`` and rows ``Y+1..Y+16``, clipped to the frame, regardless of Y (a sprite
    parked at Y=$FF simply clips away).
    """
    if len(oam_bytes) < SPRITE_COUNT * 4:
        raise ValueError(f"OAM snapshot must have 256 bytes, got {len(oam_bytes)}")
    mask = bytearray(FRAME_SIZE)
    for i in range(SPRITE_COUNT):
        y = int(oam_bytes[4 * i]) & 0xFF
        x = int(oam_bytes[4 * i + 3]) & 0xFF
        x1 = min(x + SPRITE_WIDTH, WIDTH)
        for row in range(y + 1, min(y + 1 + SPRITE_HEIGHT, HEIGHT)):
            base = row * WIDTH
            mask[base + x : base + x1] = b"\x01" * (x1 - x)
    return mask


def compare_frames(
    a: Sequence[int], b: Sequence[int], mask: Sequence[int] | None = None
) -> tuple[int, tuple[int, int] | None]:
    """Count differing unmasked pixels; also return the first (x, y) in row-major order."""
    if len(a) != FRAME_SIZE or len(b) != FRAME_SIZE:
        raise ValueError(f"frames must have {FRAME_SIZE} pixels, got {len(a)} and {len(b)}")
    if mask is not None and len(mask) != FRAME_SIZE:
        raise ValueError(f"mask must have {FRAME_SIZE} entries, got {len(mask)}")
    count = 0
    first: tuple[int, int] | None = None
    for i in range(FRAME_SIZE):
        if a[i] != b[i] and not (mask is not None and mask[i]):
            if first is None:
                first = (i % WIDTH, i // WIDTH)
            count += 1
    return count, first


def _parse_int(token: str) -> int:
    token = token.strip()
    if token.startswith("$"):
        return int(token[1:], 16)
    if token.lower().startswith("0x"):
        return int(token, 16)
    return int(token, 10)


def read_asm_bytes(path: str | Path, label: str) -> bytes:
    """Bytes of the ``.byte`` lines that follow ``label:`` in a ca65 file (e.g. nametable_N.s).

    Reading stops at the next label or at a segment/export/other directive that is not
    ``.byte``. Comments (``;``) are stripped. ``label`` is matched exactly (including a
    leading underscore, as in ``_screen0_nametable``).
    """
    out = bytearray()
    found = False
    label_re = re.compile(r"^\s*([A-Za-z_@.][\w@.]*)\s*:")
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.split(";", 1)[0].strip()
        if not line:
            continue
        m = label_re.match(line)
        if m:
            if found:
                break
            if m.group(1) == label:
                found = True
            continue
        if not found:
            continue
        if line.startswith(".byte"):
            for tok in line[len(".byte") :].split(","):
                if tok.strip():
                    out.append(_parse_int(tok))
        else:
            break
    if not found:
        raise ValueError(f"label {label!r} not found in {path}")
    return bytes(out)


def parse_assets_palettes(path_or_text: str | Path) -> dict[str, list[int]]:
    """Parse ``const unsigned char palette_*[16] = { 0x..,... };`` arrays of assets.h.

    Accepts a path to ``assets.h`` or the file text itself. Returns e.g.
    ``{"palette_bg": [16 ints], "palette_sprite": [16 ints]}``.
    """
    if isinstance(path_or_text, Path) or (
        isinstance(path_or_text, str) and "\n" not in path_or_text and Path(path_or_text).is_file()
    ):
        text = Path(path_or_text).read_text(encoding="utf-8")
    else:
        text = str(path_or_text)
    result: dict[str, list[int]] = {}
    pat = re.compile(r"const\s+unsigned\s+char\s+(palette_\w+)\s*\[\s*\d*\s*\]\s*=\s*\{([^}]*)\}")
    for m in pat.finditer(text):
        vals = [_parse_int(t) for t in m.group(2).split(",") if t.strip()]
        result[m.group(1)] = vals
    return result
