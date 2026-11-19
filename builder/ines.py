"""iNES header and ROM assembly (mapper 0 / NROM)."""

CHR_SIZE = 8192
_VALID_PRG_KB = (16, 32)
_VALID_MIRRORING = ("vertical", "horizontal")


def build_ines_header(prg_kb: int, mirroring: str) -> bytes:
    """Return the 16-byte iNES header for an NROM cartridge with 8 KB CHR."""
    if isinstance(prg_kb, bool) or prg_kb not in _VALID_PRG_KB:
        raise ValueError(f"prg_kb must be 16 or 32, got {prg_kb!r}")
    if mirroring not in _VALID_MIRRORING:
        raise ValueError(
            f"mirroring must be 'vertical' or 'horizontal', got {mirroring!r}"
        )
    flags6 = 1 if mirroring == "vertical" else 0
    return bytes([0x4E, 0x45, 0x53, 0x1A, prg_kb // 16, 1, flags6]) + bytes(9)


def assemble_rom(prg: bytes, chr_bin: bytes, prg_kb: int, mirroring: str) -> bytes:
    """Return ``header + prg + chr_bin`` after checking the section sizes."""
    header = build_ines_header(prg_kb, mirroring)
    if len(prg) != prg_kb * 1024:
        raise ValueError(
            f"PRG size is {len(prg)} bytes, expected {prg_kb * 1024} for prg_kb={prg_kb}"
        )
    if len(chr_bin) != CHR_SIZE:
        raise ValueError(f"CHR size is {len(chr_bin)} bytes, expected {CHR_SIZE}")
    return header + bytes(prg) + bytes(chr_bin)
