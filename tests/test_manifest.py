"""Unit tests for converter.manifest (Manifest loading and validation)."""

from __future__ import annotations

import copy
import json

import pytest

from converter.errors import ConversionError
from converter.manifest import load_manifest, validate_against_resources
from converter.models import (
    BGPaletteRegion,
    ImageBank,
    ManifestData,
    ObjectDef,
    PaletteDef,
    PyxresData,
    Resources,
    ScreenDef,
    SpriteDef,
    Tilemap,
)


def base_manifest() -> dict:
    return {
        "pyxres_files": ["game.pyxres"],
        "nes_colors": {"0": 15, "1": 17, "2": 33, "3": 48},
        "bg_palettes": {"bg0": [0, 1, 2, 3]},
        "sprite_palettes": {"sp0": [0, 1, 2]},
        "bg_palette_regions": [
            {"image_bank": 0, "u": 0, "v": 0, "w": 64, "h": 64, "palette": "bg0"}
        ],
        "sprites": [
            {"name": "hero", "image_bank": 0, "u": 0, "v": 0, "w": 8, "h": 16, "palette": "sp0"}
        ],
        "screens": [
            {"tilemap": 0, "x": 0, "y": 0, "count": 2, "hud_tilemap": 1, "hud_x": 0, "hud_y": 0}
        ],
    }


def write_json(tmp_path, data, name="manifest.json"):
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def load(tmp_path, data):
    return load_manifest(write_json(tmp_path, data))


def with_object(obj: dict) -> dict:
    data = base_manifest()
    data["screens"][0]["objects"] = [obj]
    return data


def resources(bank_w=16, bank_h=16, tilemaps=2) -> Resources:
    bank = ImageBank(width=bank_w, height=bank_h, pixels=())
    tm = Tilemap(width=1, height=1, imgsrc=0, cells=(((0, 0),),))
    return Resources(files=(PyxresData(images=(bank,), tilemaps=(tm,) * tilemaps),))


# --- Manifest error rows ---


def test_missing_manifest_file(tmp_path):
    missing = tmp_path / "nope.json"
    with pytest.raises(ConversionError) as exc:
        load_manifest(missing)
    assert "not found" in str(exc.value)
    assert str(missing) in str(exc.value)


def test_missing_nes_colors(tmp_path):
    data = base_manifest()
    del data["nes_colors"]
    with pytest.raises(ConversionError) as exc:
        load(tmp_path, data)
    assert "nes_colors" in str(exc.value)


@pytest.mark.parametrize("remove", [True, False])
def test_missing_or_empty_bg_palette_regions(tmp_path, remove):
    data = base_manifest()
    if remove:
        del data["bg_palette_regions"]
    else:
        data["bg_palette_regions"] = []
    with pytest.raises(ConversionError) as exc:
        load(tmp_path, data)
    assert "bg_palette_regions" in str(exc.value)


@pytest.mark.parametrize(
    "field", ["tilemap", "x", "y", "count", "hud_tilemap", "hud_x", "hud_y"]
)
def test_screen_entry_missing_field(tmp_path, field):
    data = base_manifest()
    del data["screens"][0][field]
    with pytest.raises(ConversionError) as exc:
        load(tmp_path, data)
    msg = str(exc.value)
    assert "'screens' entry 0" in msg
    assert f"'{field}'" in msg


def test_screen_count_below_one(tmp_path):
    data = base_manifest()
    data["screens"][0]["count"] = 0
    with pytest.raises(ConversionError) as exc:
        load(tmp_path, data)
    msg = str(exc.value)
    assert "entry 0" in msg
    assert "count" in msg
    assert "0" in msg


def test_sprite_width_not_multiple_of_8(tmp_path):
    data = base_manifest()
    data["sprites"][0]["w"] = 12
    with pytest.raises(ConversionError) as exc:
        load(tmp_path, data)
    msg = str(exc.value)
    assert "hero" in msg
    assert "multiple of 8" in msg
    assert "12" in msg


def test_sprite_height_not_multiple_of_16(tmp_path):
    data = base_manifest()
    data["sprites"][0]["h"] = 8
    with pytest.raises(ConversionError) as exc:
        load(tmp_path, data)
    msg = str(exc.value)
    assert "hero" in msg
    assert "multiple of 16" in msg
    assert "8" in msg


def test_undefined_sprite_palette(tmp_path):
    data = base_manifest()
    data["sprites"][0]["palette"] = "ghost"
    with pytest.raises(ConversionError) as exc:
        load(tmp_path, data)
    msg = str(exc.value)
    assert "hero" in msg
    assert "ghost" in msg
    assert "sp0" in msg


def test_undefined_bg_palette_in_region(tmp_path):
    data = base_manifest()
    data["bg_palette_regions"][0]["palette"] = "ghost"
    with pytest.raises(ConversionError) as exc:
        load(tmp_path, data)
    msg = str(exc.value)
    assert "entry 0" in msg
    assert "ghost" in msg
    assert "bg0" in msg


def test_validate_sprite_rectangle_outside_bank():
    manifest = ManifestData(
        pyxres_files=(),
        nes_colors={},
        bg_palettes=(),
        sprite_palettes=(),
        bg_palette_regions=(),
        sprites=(SpriteDef("hero", 0, 8, 0, 16, 16, "sp0"),),
        screens=(),
    )
    with pytest.raises(ConversionError) as exc:
        validate_against_resources(manifest, resources(bank_w=16, bank_h=16))
    msg = str(exc.value)
    assert "hero" in msg
    assert "u=8" in msg
    assert "bank 0" in msg
    assert "16x16" in msg


@pytest.mark.parametrize("field,tilemap,hud", [("tilemap", 5, 1), ("hud_tilemap", 0, 7)])
def test_validate_unknown_tilemap(field, tilemap, hud):
    screen = ScreenDef(tilemap=tilemap, x=0, y=0, count=1, hud_tilemap=hud, hud_x=0, hud_y=0)
    manifest = ManifestData((), {}, (), (), (), (), (screen,))
    with pytest.raises(ConversionError) as exc:
        validate_against_resources(manifest, resources(tilemaps=2))
    msg = str(exc.value)
    assert "entry 0" in msg
    assert field in msg
    assert str(tilemap if field == "tilemap" else hud) in msg


# --- Valid parsing ---


def expected_manifest(base_dir) -> ManifestData:
    return ManifestData(
        pyxres_files=(str(base_dir / "game.pyxres"),),
        nes_colors={0: 15, 1: 17, 2: 33, 3: 48},
        bg_palettes=(PaletteDef("bg0", (0, 1, 2, 3)),),
        sprite_palettes=(PaletteDef("sp0", (0, 1, 2)),),
        bg_palette_regions=(BGPaletteRegion(0, 0, 0, 64, 64, "bg0"),),
        sprites=(SpriteDef("hero", 0, 0, 0, 8, 16, "sp0"),),
        screens=(
            ScreenDef(
                tilemap=0,
                x=0,
                y=0,
                count=2,
                hud_tilemap=1,
                hud_x=0,
                hud_y=0,
                objects=(),
            ),
        ),
    )


def test_valid_json_parses(tmp_path):
    assert load(tmp_path, base_manifest()) == expected_manifest(tmp_path)


def test_valid_yaml_equals_json(tmp_path):
    yaml = pytest.importorskip("yaml")
    json_dir = tmp_path / "j"
    yaml_dir = tmp_path / "y"
    json_dir.mkdir()
    yaml_dir.mkdir()
    from_json = load(json_dir, base_manifest())
    path = yaml_dir / "manifest.yaml"
    path.write_text(yaml.safe_dump(base_manifest()), encoding="utf-8")
    from_yaml = load_manifest(path)
    assert from_yaml == expected_manifest(yaml_dir)
    assert from_yaml.nes_colors == from_json.nes_colors
    assert from_yaml.sprites == from_json.sprites
    assert from_yaml.screens == from_json.screens


# --- objects ---


def test_objects_absent_is_empty_tuple(tmp_path):
    manifest = load(tmp_path, base_manifest())
    assert manifest.screens[0].objects == ()


def test_objects_empty_list_is_empty_tuple(tmp_path):
    data = base_manifest()
    data["screens"][0]["objects"] = []
    assert load(tmp_path, data).screens[0].objects == ()


def test_object_screen_defaults_to_zero(tmp_path):
    manifest = load(tmp_path, with_object({"name": "hero", "x": 10, "y": 20}))
    assert manifest.screens[0].objects == (ObjectDef(name="hero", x=10, y=20, screen=0),)


def test_object_explicit_screen_and_bounds(tmp_path):
    manifest = load(tmp_path, with_object({"name": "hero", "x": 0, "y": 255, "screen": 1}))
    assert manifest.screens[0].objects == (ObjectDef("hero", 0, 255, 1),)


def test_object_unknown_sprite_name(tmp_path):
    with pytest.raises(ConversionError) as exc:
        load(tmp_path, with_object({"name": "villain", "x": 1, "y": 2}))
    msg = str(exc.value)
    assert "entry 0" in msg
    assert "objects item 0" in msg
    assert "villain" in msg


@pytest.mark.parametrize("field", ["x", "y"])
@pytest.mark.parametrize("value", [256, -1])
def test_object_coordinate_out_of_range(tmp_path, field, value):
    obj = {"name": "hero", "x": 1, "y": 2}
    obj[field] = value
    with pytest.raises(ConversionError) as exc:
        load(tmp_path, with_object(obj))
    msg = str(exc.value)
    assert "entry 0" in msg
    assert "objects item 0" in msg
    assert f"'{field}'" in msg
    assert str(value) in msg


@pytest.mark.parametrize("value", [2, -1])
def test_object_screen_out_of_range(tmp_path, value):
    with pytest.raises(ConversionError) as exc:
        load(tmp_path, with_object({"name": "hero", "x": 1, "y": 2, "screen": value}))
    msg = str(exc.value)
    assert "entry 0" in msg
    assert "objects item 0" in msg
    assert "'screen'" in msg
    assert str(value) in msg
    assert "count is 2" in msg


def test_base_manifest_not_mutated_by_helpers():
    # Guards the helper itself: each call returns an independent dict.
    a = base_manifest()
    b = copy.deepcopy(base_manifest())
    a["sprites"][0]["w"] = 99
    assert b["sprites"][0]["w"] == 8
    assert base_manifest()["sprites"][0]["w"] == 8
