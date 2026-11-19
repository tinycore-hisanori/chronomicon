"""Command line dispatcher: ``chrono convert ...`` and ``chrono build ...``."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from builder.errors import BuildError

DEFAULT_RUNTIME_DIR = Path(__file__).resolve().parent.parent / "runtime"

USAGE = """\
usage: chrono <command> [options]

commands:
  convert <manifest> [options]   convert Pyxel resources to console assets
  build <manifest> [-o BUILD_DIR] [--runtime-dir DIR]
                                 build a .nes ROM from a manifest

Use 'chrono <command> --help' for command options.
"""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chrono build", description="Build a .nes ROM from a manifest."
    )
    parser.add_argument("manifest", help="path to the manifest (.json or .yaml)")
    parser.add_argument(
        "-o",
        "--build-dir",
        default="build",
        help="build output directory (default: build)",
    )
    parser.add_argument(
        "--runtime-dir",
        default=str(DEFAULT_RUNTIME_DIR),
        help="runtime directory (default: %(default)s)",
    )
    return parser


def build_main(argv: Sequence[str]) -> int:
    parser = _build_parser()
    try:
        ns = parser.parse_args(list(argv))
    except SystemExit as exc:  # argparse: 0 for --help, 2 for usage errors
        return exc.code if isinstance(exc.code, int) else 2

    from builder.build import build
    from builder.config import load_build_config

    try:
        config = load_build_config(ns.manifest, ns.build_dir, ns.runtime_dir)
        build(config)
    except BuildError as exc:
        print(f"error: {exc.message}", file=sys.stderr)
        return exc.exit_code
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] == ["convert"]:
        from converter.converter import main as convert_main

        return convert_main(args[1:])
    if args[:1] == ["build"]:
        return build_main(args[1:])
    if args[:1] in (["-h"], ["--help"]):
        print(USAGE, end="")
        return 0
    print(USAGE, end="", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
