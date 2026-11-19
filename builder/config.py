"""Build configuration: manifest fields read by the ROM builder."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from converter.errors import ConversionError
from converter.manifest import read_manifest_table

from .errors import BuildError

_NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}$")
_DEVICE_NAMES = frozenset(
    ["CON", "PRN", "AUX", "NUL"]
    + [f"COM{i}" for i in range(1, 10)]
    + [f"LPT{i}" for i in range(1, 10)]
)
_MIRRORING = ("vertical", "horizontal")
_SOURCE_SUFFIXES = (".c", ".s")


def validate_name(name: object) -> str:
    """Return ``name`` if it is a safe file stem, else raise BuildError."""
    if not isinstance(name, str):
        raise BuildError("manifest field 'name' must be a string")
    if not _NAME_RE.fullmatch(name):  # fullmatch: `$` would accept a trailing "\n"
        raise BuildError(
            f"manifest field 'name' {name!r} is invalid: use 1 to 64 characters "
            "from A-Z a-z 0-9 _ . - and do not start with '.' or '-'"
        )
    if name.endswith((".", " ")):
        raise BuildError(f"manifest field 'name' {name!r} must not end with '.' or a space")
    if name.split(".", 1)[0].upper() in _DEVICE_NAMES:
        raise BuildError(f"manifest field 'name' {name!r} is a reserved Windows device name")
    return name


@dataclass(frozen=True)
class BuildConfig:
    manifest_path: Path
    name: str
    game_sources: tuple[Path, ...]  # absolute, order preserved
    prg_kb: int  # 16 or 32
    mirroring: str  # "vertical" | "horizontal"
    build_dir: Path
    runtime_dir: Path

    @property
    def assets_dir(self) -> Path:
        return self.build_dir / "assets"

    @property
    def obj_dir(self) -> Path:
        return self.build_dir / "obj"

    @property
    def rom_path(self) -> Path:
        return self.build_dir / f"{self.name}.nes"

    @property
    def map_path(self) -> Path:
        return self.build_dir / f"{self.name}.map"

    @property
    def label_path(self) -> Path:
        return self.build_dir / f"{self.name}.lbl"

    @property
    def prg_start(self) -> int:
        return 0x8000 if self.prg_kb == 32 else 0xC000

    @property
    def prg_size(self) -> int:
        return 0x7FFA if self.prg_kb == 32 else 0x3FFA


def _parse_sources(raw: object, base: Path) -> tuple[Path, ...]:
    if not isinstance(raw, list) or not raw:
        raise BuildError("manifest field 'game_sources' must be a non-empty list of file paths")
    sources: list[Path] = []
    stems: dict[str, str] = {}
    for item in raw:
        if not isinstance(item, str) or not item:
            raise BuildError(
                f"manifest field 'game_sources' entry {item!r} must be a non-empty string"
            )
        path = Path(item)
        if not path.is_absolute():
            path = base / path
        if path.suffix not in _SOURCE_SUFFIXES:
            raise BuildError(
                f"manifest field 'game_sources' entry {item!r} must end in .c or .s"
            )
        if not path.is_file():
            raise BuildError(f"manifest field 'game_sources' file not found: {path}")
        if path.stem in stems:
            raise BuildError(
                f"manifest field 'game_sources' has duplicate file name stem "
                f"{path.stem!r} ({stems[path.stem]!r} and {item!r})"
            )
        stems[path.stem] = item
        sources.append(path)
    return tuple(sources)


def load_build_config(
    manifest_path: str | Path, build_dir: str | Path, runtime_dir: str | Path
) -> BuildConfig:
    """Read and validate the builder fields of a manifest. Raises BuildError."""
    manifest = Path(manifest_path).resolve()
    try:
        table = read_manifest_table(manifest)
    except ConversionError as exc:
        raise BuildError(str(exc)) from exc

    if "name" not in table:
        raise BuildError("manifest field 'name' is missing")
    name = validate_name(table["name"])

    if "game_sources" not in table:
        raise BuildError("manifest field 'game_sources' is missing")
    sources = _parse_sources(table["game_sources"], manifest.parent)

    prg_kb = table.get("prg_kb", 32)
    if isinstance(prg_kb, bool) or not isinstance(prg_kb, int) or prg_kb not in (16, 32):
        raise BuildError(f"manifest field 'prg_kb' must be 16 or 32, got {prg_kb!r}")

    mirroring = table.get("mirroring", "vertical")
    if mirroring not in _MIRRORING:
        raise BuildError(
            f"manifest field 'mirroring' must be 'vertical' or 'horizontal', got {mirroring!r}"
        )

    return BuildConfig(
        manifest_path=manifest,
        name=name,
        game_sources=sources,
        prg_kb=prg_kb,
        mirroring=mirroring,
        build_dir=Path(build_dir),
        runtime_dir=Path(runtime_dir),
    )
