"""Tests for converter.pyxres_loader."""

from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from converter.errors import ConversionError
from converter.models import ImageBank, Tilemap
from converter.pyxres_loader import load_pyxres
from tests.pyxres_writer import write_pyxres


@st.composite
def image_banks(draw) -> ImageBank:
    width = draw(st.integers(1, 12))
    height = draw(st.integers(1, 12))
    # Small color alphabet makes trailing repeats (compressible rows) likely.
    colors = st.integers(0, 15) if draw(st.booleans()) else st.sampled_from([0, 7])
    pixels = tuple(
        tuple(draw(st.lists(colors, min_size=width, max_size=width))) for _ in range(height)
    )
    return ImageBank(width=width, height=height, pixels=pixels)


@st.composite
def tilemaps(draw) -> Tilemap:
    width = draw(st.integers(1, 10))
    height = draw(st.integers(1, 10))
    imgsrc = draw(st.integers(0, 2))
    coord = st.integers(0, 31) if draw(st.booleans()) else st.sampled_from([0, 3])
    cell = st.tuples(coord, coord)
    cells = tuple(
        tuple(draw(st.lists(cell, min_size=width, max_size=width))) for _ in range(height)
    )
    return Tilemap(width=width, height=height, imgsrc=imgsrc, cells=cells)


# Feature: asset-converter, Property 12: Pyxres loader round trip
# **Validates: Requirements 11.1, 11.2, 11.8**
@given(
    images=st.lists(image_banks(), max_size=4),
    maps=st.lists(tilemaps(), max_size=4),
    compress=st.booleans(),
)
def test_pyxres_loader_round_trip(images, maps, compress):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "game.pyxres"
        write_pyxres(path, images, maps, compress=compress)
        loaded = load_pyxres(path)
    assert loaded.images == tuple(images)
    assert loaded.tilemaps == tuple(maps)


# --- Unit tests: real Pyxel-saved sample and error cases ---
# Requirements: 7.1, 11.3, 11.4, 11.5, 11.6, 11.7

SAMPLE = Path(__file__).resolve().parent / "data" / "sample.pyxres"


def _zip_with(path: Path, entries: dict[str, str]) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name, text in entries.items():
            zf.writestr(name, text)
    return path


def _toml_zip(tmp_path: Path, toml_text: str) -> Path:
    return _zip_with(tmp_path / "game.pyxres", {"pyxel_resource.toml": toml_text})


def test_real_pyxel_sample_loads_with_expected_shape():
    if not SAMPLE.exists():
        pytest.skip("tests/data/sample.pyxres not generated (run make_sample_pyxres.py)")
    data = load_pyxres(SAMPLE)

    assert len(data.images) == 3
    assert all((b.width, b.height) == (256, 256) for b in data.images)
    assert all(len(b.pixels) == 256 and len(b.pixels[0]) == 256 for b in data.images)
    # Pixels drawn by make_sample_pyxres.py: pixels[y][x].
    bank0 = data.images[0].pixels
    assert bank0[0][0] == 1
    assert bank0[0][1] == 2
    assert bank0[5][3] == 7
    assert bank0[15][15] == 15
    assert bank0[200][200] == 0

    assert len(data.tilemaps) == 8
    assert all((t.width, t.height) == (256, 256) for t in data.tilemaps)
    # Cells drawn by the script: cells[y][x] = (tile_x, tile_y).
    cells0 = data.tilemaps[0].cells
    assert cells0[0][0] == (1, 2)
    assert cells0[3][5] == (4, 6)
    assert cells0[10][10] == (0, 0)


def test_missing_file_names_path(tmp_path):
    path = tmp_path / "nope.pyxres"
    with pytest.raises(ConversionError) as exc:
        load_pyxres(path)
    assert str(path) in str(exc.value)


def test_not_a_zip_names_path(tmp_path):
    path = tmp_path / "bad.pyxres"
    path.write_bytes(b"this is not a zip archive")
    with pytest.raises(ConversionError) as exc:
        load_pyxres(path)
    assert str(path) in str(exc.value)
    assert "zip" in str(exc.value)


def test_bad_toml_names_path(tmp_path):
    path = _toml_zip(tmp_path, "format_version = [unclosed")
    with pytest.raises(ConversionError) as exc:
        load_pyxres(path)
    assert str(path) in str(exc.value)
    assert "TOML" in str(exc.value)


def test_zip_without_resource_entry(tmp_path):
    path = _zip_with(tmp_path / "game.pyxres", {"other.txt": "hello"})
    with pytest.raises(ConversionError) as exc:
        load_pyxres(path)
    assert str(path) in str(exc.value)
    assert "pyxel_resource.toml" in str(exc.value)


def test_toml_without_images_key(tmp_path):
    path = _toml_zip(tmp_path, "format_version = 1\ntilemaps = []\n")
    with pytest.raises(ConversionError) as exc:
        load_pyxres(path)
    assert str(path) in str(exc.value)
    assert "images" in str(exc.value)


def test_unsupported_format_version(tmp_path):
    path = _toml_zip(tmp_path, "format_version = 99\nimages = []\ntilemaps = []\n")
    with pytest.raises(ConversionError) as exc:
        load_pyxres(path)
    message = str(exc.value)
    assert str(path) in message
    assert "99" in message
    assert "format_version" in message


def test_pixel_value_16_reports_path_bank_position_and_value(tmp_path):
    toml_text = (
        "format_version = 1\ntilemaps = []\n"
        "[[images]]\nwidth = 3\nheight = 2\ndata = [[0, 0, 0], [0, 16, 0]]\n"
    )
    path = _toml_zip(tmp_path, toml_text)
    with pytest.raises(ConversionError) as exc:
        load_pyxres(path)
    message = str(exc.value)
    assert str(path) in message
    assert "image bank 0" in message
    assert "(1, 1)" in message
    assert "16" in message
