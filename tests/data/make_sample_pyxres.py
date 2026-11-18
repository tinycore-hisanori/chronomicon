"""Regenerate tests/data/sample.pyxres with the real Pyxel package.

Usage: python tests/data/make_sample_pyxres.py   (needs `pip install pyxel`)

Pyxel saves 3 image banks and 8 tilemaps, each 256x256. Known content
(checked by tests/test_pyxres_loader.py), as (x, y):
  image bank 0: pixel (0, 0) = 1, (1, 0) = 2, (15, 15) = 15, (3, 5) = 7
  tilemap 0:    cell (0, 0) = (1, 2), cell (5, 3) = (4, 6)
"""

from __future__ import annotations

from pathlib import Path

import pyxel

OUT = Path(__file__).resolve().parent / "sample.pyxres"

IMAGE_PIXELS = {(0, 0): 1, (1, 0): 2, (15, 15): 15, (3, 5): 7}
TILE_CELLS = {(0, 0): (1, 2), (5, 3): (4, 6)}


def main() -> None:
    pyxel.init(16, 16, title="make_sample_pyxres")
    for (x, y), color in IMAGE_PIXELS.items():
        pyxel.images[0].pset(x, y, color)
    for (x, y), tile in TILE_CELLS.items():
        pyxel.tilemaps[0].pset(x, y, tile)
    pyxel.save(str(OUT))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
