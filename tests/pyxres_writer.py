"""Test helper: write a minimal .pyxres archive (zip with one TOML entry).

The TOML is serialised by hand (integers and arrays only), so tests need no
TOML writer dependency. With ``compress=True`` Pyxel's trailing-repeat
compression is applied so the loader's expansion is exercised.
"""

from __future__ import annotations

import zipfile
from collections.abc import Sequence
from pathlib import Path

from converter.models import ImageBank, Tilemap

ENTRY_NAME = "pyxel_resource.toml"
FORMAT_VERSION = 1


def _compress_row(row: Sequence[int]) -> list[int]:
    """Drop trailing values equal to the last distinct run's value, keeping one."""
    values = list(row)
    while len(values) > 1 and values[-1] == values[-2]:
        values.pop()
    return values


def _compress_rows(rows: Sequence[Sequence[int]]) -> list[list[int]]:
    """Compress each row, then drop trailing rows equal to the previous row."""
    compressed = [_compress_row(row) for row in rows]
    while len(compressed) > 1 and compressed[-1] == compressed[-2]:
        compressed.pop()
    return compressed


def _toml_rows(rows: Sequence[Sequence[int]]) -> str:
    lines = ["  [" + ", ".join(str(int(v)) for v in row) + "]," for row in rows]
    return "[\n" + "\n".join(lines) + "\n]" if lines else "[]"


def _flatten_cells(row: Sequence[tuple[int, int]]) -> list[int]:
    return [v for cell in row for v in cell]


def write_pyxres(
    path: str | Path,
    images: Sequence[ImageBank],
    tilemaps: Sequence[Tilemap],
    compress: bool = False,
) -> None:
    """Write ``images`` and ``tilemaps`` to ``path`` as a .pyxres zip archive."""
    out = [f"format_version = {FORMAT_VERSION}"]
    # Top-level keys must precede any [[table]]; the loader requires both keys to exist.
    if not images:
        out.append("images = []")
    if not tilemaps:
        out.append("tilemaps = []")
    out.append("")

    for bank in images:
        rows = [list(r) for r in bank.pixels]
        if compress:
            rows = _compress_rows(rows)
        out += [
            "[[images]]",
            f"width = {bank.width}",
            f"height = {bank.height}",
            f"data = {_toml_rows(rows)}",
            "",
        ]

    for tm in tilemaps:
        rows = [_flatten_cells(r) for r in tm.cells]
        if compress:
            rows = _compress_rows(rows)
        out += [
            "[[tilemaps]]",
            f"width = {tm.width}",
            f"height = {tm.height}",
            f"imgsrc = {tm.imgsrc}",
            f"data = {_toml_rows(rows)}",
            "",
        ]

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(ENTRY_NAME, "\n".join(out))
