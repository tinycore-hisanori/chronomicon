"""Manifest loader and validator (JSON or YAML).

Manifest layout (top-level keys):

    pyxres_files        list of paths, relative to the Manifest file
    nes_colors          table: Pyxel color index -> NES 2C02 byte (required)
    bg_palettes         palettes, either {name: [colors]} or [{name, colors}]
    sprite_palettes     same shape as bg_palettes
    bg_palette_regions  list of {image_bank, u, v, w, h, palette}
    sprites             list of {name, image_bank, u, v, w, h, palette}
    screens             list of {tilemap, x, y, count, hud_tilemap, hud_x, hud_y,
                                 objects?: [{name, x, y, screen?}]}

All checks are fail-fast and raise ConversionError.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from converter.errors import ConversionError
from converter.models import (
    BGPaletteRegion,
    ManifestData,
    ObjectDef,
    PaletteDef,
    Resources,
    ScreenDef,
    SpriteDef,
)

_C_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_SCREEN_FIELDS = ("tilemap", "x", "y", "count", "hud_tilemap", "hud_x", "hud_y")
_SPRITE_FIELDS = ("name", "image_bank", "u", "v", "w", "h", "palette")
_REGION_FIELDS = ("image_bank", "u", "v", "w", "h", "palette")


# --- Helpers ---


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _require_int(value: Any, where: str, field: str) -> int:
    if not _is_int(value):
        raise ConversionError(
            f"{where}: field '{field}' must be an integer, got {value!r}"
        )
    return value


def _require_str(value: Any, where: str, field: str) -> str:
    if not isinstance(value, str):
        raise ConversionError(
            f"{where}: field '{field}' must be a string, got {value!r}"
        )
    return value


def _require_list(value: Any, key: str) -> list:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ConversionError(f"Manifest field '{key}' must be a list, got {value!r}")
    return value


def _require_item(item: Any, where: str) -> dict:
    if not isinstance(item, dict):
        raise ConversionError(f"{where}: expected a table, got {item!r}")
    return item


def _read_raw(path: Path) -> dict:
    if not path.is_file():
        raise ConversionError(f"Manifest file not found: {path}")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ConversionError(f"Manifest file cannot be read: {path} ({exc})") from exc

    suffix = path.suffix.lower()
    try:
        if suffix == ".json":
            raw = json.loads(text)
        elif suffix in (".yaml", ".yml"):
            try:
                import yaml
            except ImportError as exc:
                raise ConversionError(
                    f"Manifest {path} is YAML but PyYAML is not installed"
                ) from exc
            raw = yaml.safe_load(text)
        else:
            raise ConversionError(
                f"Manifest file {path} has unsupported extension '{path.suffix}' "
                "(expected .json, .yaml or .yml)"
            )
    except ConversionError:
        raise
    except Exception as exc:  # json.JSONDecodeError, yaml.YAMLError
        raise ConversionError(f"Manifest file {path} is malformed: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConversionError(f"Manifest file {path} must contain a table at top level")
    return raw


def _parse_nes_colors(raw: dict) -> dict[int, int]:
    if "nes_colors" not in raw or raw["nes_colors"] is None:
        raise ConversionError("Manifest is missing required field 'nes_colors'")
    table = raw["nes_colors"]
    if not isinstance(table, dict):
        raise ConversionError(f"Manifest field 'nes_colors' must be a table, got {table!r}")
    result: dict[int, int] = {}
    for key, value in table.items():
        try:
            index = key if _is_int(key) else int(str(key), 10)
        except ValueError as exc:
            raise ConversionError(
                f"Manifest 'nes_colors' key {key!r} is not a Pyxel color index"
            ) from exc
        if not _is_int(value):
            raise ConversionError(
                f"Manifest 'nes_colors' value for color {index} must be an integer, got {value!r}"
            )
        result[index] = value
    return result


def _parse_palettes(raw: dict, key: str) -> tuple[PaletteDef, ...]:
    data = raw.get(key)
    if data is None:
        return ()
    pairs: list[tuple[str, Any]] = []
    if isinstance(data, dict):
        pairs = [(str(name), colors) for name, colors in data.items()]
    elif isinstance(data, list):
        for pos, item in enumerate(data):
            where = f"Manifest '{key}' entry {pos}"
            item = _require_item(item, where)
            for field in ("name", "colors"):
                if field not in item:
                    raise ConversionError(f"{where}: missing field '{field}'")
            pairs.append((_require_str(item["name"], where, "name"), item["colors"]))
    else:
        raise ConversionError(f"Manifest field '{key}' must be a table or a list, got {data!r}")

    palettes: list[PaletteDef] = []
    seen: set[str] = set()
    for name, colors in pairs:
        where = f"Manifest '{key}' palette '{name}'"
        if name in seen:
            raise ConversionError(f"{where}: duplicate palette name")
        seen.add(name)
        if not isinstance(colors, list):
            raise ConversionError(f"{where}: colors must be a list, got {colors!r}")
        for color in colors:
            _require_int(color, where, "colors")
        palettes.append(PaletteDef(name=name, pyxel_colors=tuple(colors)))
    return tuple(palettes)


def _check_fields(item: dict, fields: tuple[str, ...], where: str) -> None:
    for field in fields:
        if field not in item or item[field] is None:
            raise ConversionError(f"{where}: missing field '{field}'")


def _parse_regions(raw: dict) -> tuple[BGPaletteRegion, ...]:
    items = _require_list(raw.get("bg_palette_regions"), "bg_palette_regions")
    if not items:
        raise ConversionError(
            "Manifest defines no BG palette assignment: "
            "'bg_palette_regions' is missing or empty"
        )
    regions = []
    for pos, item in enumerate(items):
        where = f"Manifest 'bg_palette_regions' entry {pos}"
        item = _require_item(item, where)
        _check_fields(item, _REGION_FIELDS, where)
        nums = [_require_int(item[f], where, f) for f in _REGION_FIELDS[:-1]]
        palette = _require_str(item["palette"], where, "palette")
        regions.append(BGPaletteRegion(*nums, palette=palette))
    return tuple(regions)


def _parse_screens(raw: dict) -> list[tuple[dict[str, int], Any]]:
    """Return (numeric fields, raw objects) per entry; objects are parsed later."""
    items = _require_list(raw.get("screens"), "screens")
    screens = []
    for pos, item in enumerate(items):
        where = f"Manifest 'screens' entry {pos}"
        item = _require_item(item, where)
        _check_fields(item, _SCREEN_FIELDS, where)
        nums = {f: _require_int(item[f], where, f) for f in _SCREEN_FIELDS}
        if nums["count"] < 1:
            raise ConversionError(
                f"{where}: field 'count' must be at least 1, got {nums['count']}"
            )
        screens.append((nums, item.get("objects")))
    return screens


def _parse_sprites(raw: dict) -> tuple[SpriteDef, ...]:
    items = _require_list(raw.get("sprites"), "sprites")
    sprites = []
    for pos, item in enumerate(items):
        where = f"Manifest 'sprites' entry {pos}"
        item = _require_item(item, where)
        _check_fields(item, _SPRITE_FIELDS, where)
        name = _require_str(item["name"], where, "name")
        where = f"Sprite '{name}'"
        nums = [_require_int(item[f], where, f) for f in ("image_bank", "u", "v", "w", "h")]
        palette = _require_str(item["palette"], where, "palette")
        sprites.append(SpriteDef(name, *nums, palette=palette))
    return tuple(sprites)


def _check_sprites(sprites: tuple[SpriteDef, ...], sprite_palettes: tuple[PaletteDef, ...]) -> None:
    defined = {p.name for p in sprite_palettes}
    for sprite in sprites:
        if sprite.w <= 0 or sprite.w % 8 != 0:
            raise ConversionError(
                f"Sprite '{sprite.name}': w must be a positive multiple of 8, got {sprite.w}"
            )
        if sprite.h <= 0 or sprite.h % 16 != 0:
            raise ConversionError(
                f"Sprite '{sprite.name}': h must be a positive multiple of 16, got {sprite.h}"
            )
        if sprite.palette not in defined:
            raise ConversionError(
                f"Sprite '{sprite.name}': palette '{sprite.palette}' is not a defined "
                f"sprite palette (defined: {sorted(defined)})"
            )


def _check_sprite_names(sprites: tuple[SpriteDef, ...]) -> None:
    seen: set[str] = set()
    for sprite in sprites:
        name = sprite.name
        if not _C_IDENT.match(name):
            raise ConversionError(f"Sprite name '{name}' is not a valid C identifier")
        if name in seen:
            raise ConversionError(f"Sprite name '{name}' is defined more than once")
        seen.add(name)


def _check_regions(
    regions: tuple[BGPaletteRegion, ...], bg_palettes: tuple[PaletteDef, ...]
) -> None:
    defined = {p.name for p in bg_palettes}
    for pos, region in enumerate(regions):
        if region.palette not in defined:
            raise ConversionError(
                f"bg_palette_regions entry {pos} (bank {region.image_bank}, "
                f"u={region.u}, v={region.v}, w={region.w}, h={region.h}): "
                f"palette '{region.palette}' is not a defined BG palette "
                f"(defined: {sorted(defined)})"
            )


def _parse_objects(
    entry_pos: int,
    count: int,
    raw_objects: Any,
    sprite_names: set[str],
) -> tuple[ObjectDef, ...]:
    if raw_objects is None:
        return ()
    where_entry = f"Manifest 'screens' entry {entry_pos}"
    if not isinstance(raw_objects, list):
        raise ConversionError(f"{where_entry}: field 'objects' must be a list, got {raw_objects!r}")
    objects = []
    for item_pos, item in enumerate(raw_objects):
        where = f"{where_entry}, objects item {item_pos}"
        item = _require_item(item, where)
        for field in ("name", "x", "y"):
            if field not in item or item[field] is None:
                raise ConversionError(f"{where}: missing field '{field}'")
        name = _require_str(item["name"], where, "name")
        if name not in sprite_names:
            raise ConversionError(f"{where}: unknown sprite name '{name}'")
        x = _require_int(item["x"], where, "x")
        y = _require_int(item["y"], where, "y")
        for field, value in (("x", x), ("y", y)):
            if not 0 <= value <= 255:
                raise ConversionError(
                    f"{where}: field '{field}' must be in 0-255, got {value}"
                )
        screen = item.get("screen")
        screen = 0 if screen is None else _require_int(screen, where, "screen")
        if not 0 <= screen < count:
            raise ConversionError(
                f"{where}: field 'screen' must be in 0-{count - 1} "
                f"(entry count is {count}), got {screen}"
            )
        objects.append(ObjectDef(name=name, x=x, y=y, screen=screen))
    return tuple(objects)


# --- Public API ---


def load_manifest(path: str | Path) -> ManifestData:
    """Read JSON or YAML (by extension) and validate everything that does not need
    the loaded banks. Raises ConversionError."""
    path = Path(path)
    raw = _read_raw(path)

    nes_colors = _parse_nes_colors(raw)
    regions = _parse_regions(raw)
    screen_sources = _parse_screens(raw)
    sprites = _parse_sprites(raw)
    bg_palettes = _parse_palettes(raw, "bg_palettes")
    sprite_palettes = _parse_palettes(raw, "sprite_palettes")

    _check_sprites(sprites, sprite_palettes)
    _check_sprite_names(sprites)
    _check_regions(regions, bg_palettes)

    sprite_names = {s.name for s in sprites}
    screens = tuple(
        ScreenDef(**nums, objects=_parse_objects(pos, nums["count"], objs, sprite_names))
        for pos, (nums, objs) in enumerate(screen_sources)
    )

    files = _require_list(raw.get("pyxres_files"), "pyxres_files")
    base = path.parent
    pyxres_files = []
    for entry in files:
        if not isinstance(entry, str):
            raise ConversionError(f"Manifest 'pyxres_files' entry must be a string, got {entry!r}")
        pyxres_files.append(str((base / entry)))

    return ManifestData(
        pyxres_files=tuple(pyxres_files),
        nes_colors=nes_colors,
        bg_palettes=bg_palettes,
        sprite_palettes=sprite_palettes,
        bg_palette_regions=regions,
        sprites=sprites,
        screens=screens,
    )


def validate_against_resources(manifest: ManifestData, resources: Resources) -> None:
    """Validate everything that needs the loaded banks and tilemaps:
    sprite rectangles inside their bank, screen/HUD tilemap numbers that exist."""
    for sprite in manifest.sprites:
        bank = resources.image_bank(sprite.image_bank)
        if bank is None:
            raise ConversionError(
                f"Sprite '{sprite.name}': image bank {sprite.image_bank} does not exist"
            )
        if (
            sprite.u < 0
            or sprite.v < 0
            or sprite.u + sprite.w > bank.width
            or sprite.v + sprite.h > bank.height
        ):
            raise ConversionError(
                f"Sprite '{sprite.name}': rectangle (u={sprite.u}, v={sprite.v}, "
                f"w={sprite.w}, h={sprite.h}) is outside image bank {sprite.image_bank} "
                f"of size {bank.width}x{bank.height}"
            )

    for pos, screen in enumerate(manifest.screens):
        for field, number in (("tilemap", screen.tilemap), ("hud_tilemap", screen.hud_tilemap)):
            if resources.tilemap(number) is None:
                raise ConversionError(
                    f"Manifest 'screens' entry {pos}: {field} {number} was not "
                    "returned by the loaded .pyxres files"
                )
