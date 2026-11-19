"""Orchestrator and CLI entry point: runs every converter stage in design order."""

from __future__ import annotations

import argparse
import sys
import zlib
from collections.abc import Sequence
from pathlib import Path

from converter import (
    attribute,
    chr_encoder,
    emitter,
    font_mapper,
    manifest as manifest_mod,
    metasprite,
    nametable,
    palette,
    palette_map,
    pyxres_loader,
)
from converter.errors import ConversionError
from converter.models import (
    ConversionResult,
    EmitResult,
    MetaspriteTable,
    PaletteSet,
    Resources,
)


def _crc_line(name: str, data: bytes) -> str:
    return f"{name}: {len(data)} bytes, crc32={zlib.crc32(data) & 0xFFFFFFFF:08x}"


def _metasprite_blocks(table: MetaspriteTable) -> list[tuple[str, bytes]]:
    blocks = []
    for entry in table.entries:
        data = bytearray()
        for hw in entry.hw_sprites:
            data += bytes(
                (hw.x_offset & 0xFF, hw.y_offset & 0xFF, hw.oam_tile & 0xFF, hw.attributes & 0xFF)
            )
        suffix = "_flip" if entry.is_flip else ""
        blocks.append((f"metasprite_{entry.name}{suffix}", bytes(data)))
    return blocks


def _asset_log_lines(result: ConversionResult, emit: EmitResult) -> list[str]:
    lines = []
    for name in emit.files:
        lines.append(f"{name}: {emit.byte_lengths[name]} bytes, crc32={emit.checksums[name]}")
    lines.append(_crc_line("chr_bg", result.chr_bin[:4096]))
    lines.append(_crc_line("chr_sprite", result.chr_bin[4096:]))
    for nt in result.nametables:
        lines.append(_crc_line(f"nametable[{nt.screen_index}]", bytes(nt.tile_ids)))
    for at in result.attr_tables:
        lines.append(_crc_line(f"attr[{at.screen_index}]", at.data))
    bg, spr = emitter.palette_arrays(result.palette_set)
    lines.append(_crc_line("palette_bg", bytes(bg)))
    lines.append(_crc_line("palette_sprite", bytes(spr)))
    for name, data in _metasprite_blocks(result.metasprites):
        lines.append(_crc_line(name, data))
    return lines


def run_pipeline(
    pyxres_override: Sequence[str | Path] | None,
    manifest_path: str | Path,
    out_dir: str | Path,
) -> tuple[ConversionResult, EmitResult]:
    """Run all stages. Raises ConversionError."""
    manifest = manifest_mod.load_manifest(manifest_path)
    files = list(pyxres_override) if pyxres_override else list(manifest.pyxres_files)
    resources = Resources(files=tuple(pyxres_loader.load_pyxres(p) for p in files))
    manifest_mod.validate_against_resources(manifest, resources)

    palette_set: PaletteSet = palette.build_palettes(manifest)
    layouts = palette_map.build_screen_layouts(manifest, resources, palette_set)
    bg = chr_encoder.encode_bg_tiles(layouts, resources, palette_set, manifest)
    bg_chr = font_mapper.encode_font(bytearray(bg.chr_bytes))
    spr = chr_encoder.encode_sprite_tiles(manifest.sprites, resources, palette_set)
    nametables = nametable.build_nametables(layouts, bg.tile_to_chr_id)
    attrs = [
        attribute.build_attribute_table(lay.screen_index, [list(r) for r in lay.palette_map])
        for lay in layouts
    ]
    metas = metasprite.build_metasprites(manifest.sprites, spr, palette_set)

    result = ConversionResult(
        chr_bin=bytes(bg_chr) + bytes(spr.chr_bytes),
        palette_set=palette_set,
        nametables=tuple(nametables),
        attr_tables=tuple(attrs),
        metasprites=metas,
        screens=manifest.screens,
        sprite_names=tuple(s.name for s in manifest.sprites),
    )
    emit = emitter.emit_all(result, Path(out_dir))
    return result, emit


def convert(
    pyxres_override: Sequence[str | Path] | None,
    manifest_path: str | Path,
    out_dir: str | Path,
) -> int:
    """Convert a game. Returns 0 on success, 1 after printing `error: <message>` to stderr."""
    try:
        result, emit = run_pipeline(pyxres_override, manifest_path, out_dir)
    except ConversionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: {exc.filename or out_dir}: {exc}", file=sys.stderr)
        return 1
    for line in _asset_log_lines(result, emit):
        print(line)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="chrono", description="Convert Pyxel resources to 8-bit console assets."
    )
    parser.add_argument("manifest", help="Manifest file (JSON or YAML)")
    parser.add_argument("-o", "--out-dir", default="build", help="output directory")
    parser.add_argument(
        "--pyxres", nargs="+", default=None, help="override the Manifest pyxres_files list"
    )
    args = parser.parse_args(argv)
    return convert(args.pyxres, args.manifest, args.out_dir)


if __name__ == "__main__":
    sys.exit(main())
