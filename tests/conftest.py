"""Pytest configuration: Hypothesis profiles.

Select a profile with the HYPOTHESIS_PROFILE environment variable (default: dev).
  dev: 25 examples per property, keeps the whole suite under 60 seconds.
  ci:  200 examples per property.
"""

from __future__ import annotations

import os

from hypothesis import settings

settings.register_profile("dev", max_examples=25, deadline=None)
settings.register_profile("ci", max_examples=200, deadline=None)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))


# ---------------------------------------------------------------------------
# Session fixtures for the ROM tests (rom-builder). All of them are lazy: a test
# that does not request one never builds a ROM or starts Node.
# ---------------------------------------------------------------------------

from dataclasses import dataclass  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class BuiltRom:
    """Result of one session-wide ROM build."""

    nes: Path
    map: Path
    lbl: Path
    build_dir: Path
    assets_dir: Path


def _toolchain_unavailable(message: str) -> None:
    """Skip, or fail when CHRONO_REQUIRE_TOOLCHAIN=1."""
    if os.environ.get("CHRONO_REQUIRE_TOOLCHAIN") == "1":
        pytest.fail(message)
    pytest.skip(message)


@pytest.fixture(scope="session")
def rom_project(tmp_path_factory: pytest.TempPathFactory):
    """The deterministic ROM test project (one .pyxres, three manifests)."""
    from tests.rom_fixtures import write_project

    return write_project(tmp_path_factory.mktemp("rom_project"))


@pytest.fixture(scope="session")
def rom_tools():
    """cc65 tool paths; skips (or fails with CHRONO_REQUIRE_TOOLCHAIN=1) when missing."""
    from builder.errors import BuildError
    from builder.tools import find_tools

    try:
        return find_tools()
    except BuildError as exc:
        _toolchain_unavailable(f"cc65 toolchain not available: {exc}")


def _build_rom(rom_project, rom_tools, tmp_path_factory, manifest_attr: str) -> BuiltRom:
    from builder.build import build
    from builder.config import load_build_config

    manifest = getattr(rom_project, manifest_attr)
    build_dir = tmp_path_factory.mktemp(f"build_{manifest.stem}")
    config = load_build_config(manifest, build_dir, _REPO_ROOT / "runtime")
    result = build(config, tools=rom_tools, log=lambda _msg: None)
    return BuiltRom(
        nes=result.rom_path,
        map=result.map_path,
        lbl=result.label_path,
        build_dir=build_dir,
        assets_dir=config.assets_dir,
    )


@pytest.fixture(scope="session")
def boot_rom(rom_project, rom_tools, tmp_path_factory) -> BuiltRom:
    return _build_rom(rom_project, rom_tools, tmp_path_factory, "boot_manifest")


@pytest.fixture(scope="session")
def password_rom(rom_project, rom_tools, tmp_path_factory) -> BuiltRom:
    return _build_rom(rom_project, rom_tools, tmp_path_factory, "password_manifest")


@pytest.fixture(scope="session")
def runtime_rom(rom_project, rom_tools, tmp_path_factory) -> BuiltRom:
    return _build_rom(rom_project, rom_tools, tmp_path_factory, "runtime_manifest")


def _started_runner(rom: BuiltRom):
    from tests.rom_harness import RomRunner, need_node

    need_node()  # skips or fails (CHRONO_REQUIRE_TOOLCHAIN=1) when Node is missing
    with RomRunner(rom.nes) as runner:
        yield runner


@pytest.fixture(scope="session")
def boot_runner(boot_rom):
    yield from _started_runner(boot_rom)


@pytest.fixture(scope="session")
def password_runner(password_rom):
    yield from _started_runner(password_rom)


@pytest.fixture(scope="session")
def runtime_runner(runtime_rom):
    yield from _started_runner(runtime_rom)
