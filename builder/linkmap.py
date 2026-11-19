"""Parsers for ld65 output: map file segment list, overflow warning, label file.

All functions are pure (text in, data out) so they can be tested without cc65.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Segments whose bytes live in the PRG window at their listed address.
# DATA is listed at its run address in RAM, so it is not visible here.
PRG_SEGMENTS = ("STARTUP", "CODE", "RODATA", "ONCE", "LOWCODE")

_HEX6 = r"([0-9A-Fa-f]{6})"
_ROW_RE = re.compile(rf"^(\w+)\s+{_HEX6}\s+{_HEX6}\s+{_HEX6}\s+[0-9A-Fa-f]+\s*$")
_OVERFLOW_RE = re.compile(
    r"Segment\s+\W*(\w+)\W*\s+overflows memory area\s+\W*(\w+)\W*\s+by\s+(\d+)\s+bytes?"
)
_LABEL_RE = re.compile(r"^al\s+([0-9A-Fa-f]+)\s+\.(\S+)\s*$")


@dataclass(frozen=True)
class Segment:
    """One row of the map file's "Segment list"."""

    name: str
    start: int
    end: int
    size: int


@dataclass(frozen=True)
class Overflow:
    """A PRG overflow: the culprit segment and the number of excess bytes."""

    segment: str
    bytes: int


def parse_segment_list(text: str) -> list[Segment]:
    """Parse the "Segment list:" table of an ld65 map file.

    Rows are ``Name Start End Size Align`` with hex numbers. If the text has no
    "Segment list:" header, every matching row in the text is returned.
    """
    lines = text.splitlines()
    begin = 0
    for i, line in enumerate(lines):
        if line.strip() == "Segment list:":
            begin = i + 1
            break
    segments: list[Segment] = []
    seen_row = False
    for line in lines[begin:]:
        m = _ROW_RE.match(line.strip())
        if m:
            seen_row = True
            segments.append(
                Segment(m.group(1), int(m.group(2), 16), int(m.group(3), 16), int(m.group(4), 16))
            )
        elif seen_row and not line.strip():
            break  # blank line after the table ends the section
    return segments


def find_overflow(segments: list[Segment], prg_start: int, prg_size: int) -> Overflow | None:
    """Return the PRG overflow implied by a segment list, or None if it fits.

    The culprit is the first PRG segment (by start address) whose end passes
    ``prg_start + prg_size``; the byte count is the highest end + 1 among the
    PRG segments minus that limit. Empty segments are ignored.
    """
    limit = prg_start + prg_size
    prg = sorted(
        (s for s in segments if s.name in PRG_SEGMENTS and s.size > 0),
        key=lambda s: s.start,
    )
    over = [s for s in prg if s.end + 1 > limit]
    if not over:
        return None
    top = max(s.end + 1 for s in prg)
    return Overflow(over[0].name, top - limit)


def parse_ld65_overflow(stderr: str) -> Overflow | None:
    """Parse ``Segment 'X' overflows memory area 'PRG' by N bytes`` from ld65 stderr.

    Tolerates ASCII quotes, UTF-8 curly quotes, or no quotes at all.
    """
    m = _OVERFLOW_RE.search(stderr)
    if not m:
        return None
    return Overflow(m.group(1), int(m.group(3)))


def parse_labels(text: str) -> dict[str, int]:
    """Parse an ld65 ``-Ln`` label file (``al 000300 .name``) into ``{name: address}``."""
    labels: dict[str, int] = {}
    for line in text.splitlines():
        m = _LABEL_RE.match(line.strip())
        if m:
            labels[m.group(2)] = int(m.group(1), 16)
    return labels
