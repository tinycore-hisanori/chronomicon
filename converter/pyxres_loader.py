"""Pyxres_Loader: read image banks and tilemaps from a Pyxel .pyxres file.

A .pyxres file is a zip archive with one TOML entry. It is read with `zipfile` and
`tomllib` only; `pyxel` is never imported.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - depends on the interpreter
    import tomli as tomllib  # type: ignore[no-redef]

from .errors import ConversionError
from .models import ImageBank, PyxresData, Tilemap


@dataclass(frozen=True)
class PyxresSchema:
    """Every name of the .pyxres layout that the loader depends on."""

    archive_entry: str
    version_key: str
    max_format_version: int
    images_key: str
    tilemaps_key: str
    width_key: str
    height_key: str
    data_key: str
    imgsrc_key: str


PYXRES_SCHEMA = PyxresSchema(
    archive_entry="pyxel_resource.toml",
    version_key="format_version",
    max_format_version=4,
    images_key="images",
    tilemaps_key="tilemaps",
    width_key="width",
    height_key="height",
    data_key="data",
    imgsrc_key="imgsrc",
)

_MAX_COLOR = 15


def load_pyxres(path: str | Path) -> PyxresData:
    """Return the image banks and tilemaps of `path` in file order.

    Raises ConversionError (message contains the path) when the file cannot be read, is
    not a zip archive, has malformed TOML, lacks an expected entry or key, uses an
    unsupported format version, or holds a pixel value outside 0-15.
    """
    path = Path(path)
    doc = _read_toml(path)
    schema = PYXRES_SCHEMA

    version = _require(doc, schema.version_key, path, "top level")
    if isinstance(version, bool) or not isinstance(version, int):
        raise ConversionError(f"{path}: '{schema.version_key}' must be an integer, got {version!r}")
    if version > schema.max_format_version:
        raise ConversionError(
            f"{path}: unsupported {schema.version_key} {version} "
            f"(supported up to {schema.max_format_version})"
        )

    images = tuple(
        _load_image(path, bank, table)
        for bank, table in enumerate(_tables(doc, schema.images_key, path))
    )
    tilemaps = tuple(
        _load_tilemap(path, number, table)
        for number, table in enumerate(_tables(doc, schema.tilemaps_key, path))
    )
    return PyxresData(images=images, tilemaps=tilemaps)


# --- Archive and TOML ---


def _read_toml(path: Path) -> dict[str, Any]:
    entry = PYXRES_SCHEMA.archive_entry
    try:
        with zipfile.ZipFile(path) as archive:
            try:
                raw = archive.read(entry)
            except KeyError:
                raise ConversionError(f"{path}: missing entry '{entry}' in archive") from None
    except zipfile.BadZipFile:
        raise ConversionError(f"{path}: not a valid zip archive") from None
    except OSError as exc:
        raise ConversionError(f"{path}: cannot be read ({exc.strerror or exc})") from None
    except (zipfile.LargeZipFile, RuntimeError, EOFError, ValueError) as exc:
        # Corrupt, encrypted or truncated archive members.
        raise ConversionError(f"{path}: cannot read '{entry}' from archive ({exc})") from None

    try:
        return tomllib.loads(raw.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise ConversionError(f"{path}: malformed TOML in '{entry}' ({exc})") from None


def _require(table: dict[str, Any], key: str, path: Path, where: str) -> Any:
    if key not in table:
        raise ConversionError(f"{path}: missing entry '{key}' ({where})")
    return table[key]


def _tables(doc: dict[str, Any], key: str, path: Path) -> list[dict[str, Any]]:
    tables = _require(doc, key, path, "top level")
    if not isinstance(tables, list) or not all(isinstance(t, dict) for t in tables):
        raise ConversionError(f"{path}: '{key}' must be an array of tables")
    return tables


def _int_field(table: dict[str, Any], key: str, path: Path, where: str, minimum: int) -> int:
    value = _require(table, key, path, where)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ConversionError(f"{path}: {where}: '{key}' must be an integer >= {minimum}, got {value!r}")
    return value


def _rows(table: dict[str, Any], path: Path, where: str) -> list[list[int]]:
    data = _require(table, PYXRES_SCHEMA.data_key, path, where)
    if not isinstance(data, list) or not all(isinstance(r, list) for r in data):
        raise ConversionError(f"{path}: {where}: '{PYXRES_SCHEMA.data_key}' must be an array of rows")
    for r, row in enumerate(data):
        for value in row:
            if isinstance(value, bool) or not isinstance(value, int):
                raise ConversionError(f"{path}: {where}: row {r} holds non-integer value {value!r}")
    return data


# --- Compression ---


def _expand_row(row: list[int], length: int) -> list[int]:
    """Repeat the last value of `row` up to `length` values (None when it cannot be done)."""
    if len(row) > length or (not row and length > 0):
        return None  # type: ignore[return-value]
    return row + [row[-1]] * (length - len(row)) if row else []


def _expand_rows(
    rows: list[list[int]], width: int, height: int, path: Path, where: str
) -> list[list[int]]:
    """Expand trailing-repeat compression of rows and of the row list."""
    if len(rows) > height or (not rows and height > 0):
        raise ConversionError(
            f"{path}: {where}: expected 1 to {height} rows of data, got {len(rows)}"
        )
    expanded: list[list[int]] = []
    for r, row in enumerate(rows):
        full = _expand_row(row, width)
        if full is None:
            raise ConversionError(
                f"{path}: {where}: row {r} has {len(row)} values, expected 1 to {width}"
            )
        expanded.append(full)
    expanded.extend(list(expanded[-1]) for _ in range(height - len(expanded)))
    return expanded


# --- Images and tilemaps ---


def _load_image(path: Path, bank: int, table: dict[str, Any]) -> ImageBank:
    schema = PYXRES_SCHEMA
    where = f"image bank {bank}"
    width = _int_field(table, schema.width_key, path, where, 1)
    height = _int_field(table, schema.height_key, path, where, 1)
    pixels = _expand_rows(_rows(table, path, where), width, height, path, where)
    for y, row in enumerate(pixels):
        for x, value in enumerate(row):
            if not 0 <= value <= _MAX_COLOR:
                raise ConversionError(
                    f"{path}: image bank {bank}, pixel ({x}, {y}): "
                    f"value {value} is outside 0-{_MAX_COLOR}"
                )
    return ImageBank(width=width, height=height, pixels=tuple(tuple(row) for row in pixels))


def _load_tilemap(path: Path, number: int, table: dict[str, Any]) -> Tilemap:
    schema = PYXRES_SCHEMA
    where = f"tilemap {number}"
    width = _int_field(table, schema.width_key, path, where, 1)
    height = _int_field(table, schema.height_key, path, where, 1)
    imgsrc = _int_field(table, schema.imgsrc_key, path, where, 0)
    values = _expand_rows(_rows(table, path, where), 2 * width, height, path, where)
    cells = tuple(tuple((row[2 * i], row[2 * i + 1]) for i in range(width)) for row in values)
    return Tilemap(width=width, height=height, imgsrc=imgsrc, cells=cells)
