#!/usr/bin/env python3
# SPDX-License-Identifier: CC0-1.0
"""Generate a tiny CC0 NES NROM used only for structural build tests.

The program disables rendering and loops forever. It is not a playable game and
must never be presented as gameplay validation.
"""

import argparse
from pathlib import Path


def build_rom() -> bytes:
    header = b"NES\x1a" + bytes([1, 1, 0, 0]) + bytes(8)
    prg = bytearray([0xEA] * (16 * 1024))
    program = bytes(
        [
            0x78,              # SEI
            0xD8,              # CLD
            0xA2, 0x40,        # LDX #$40
            0x8E, 0x17, 0x40,  # STX $4017
            0xA2, 0xFF,        # LDX #$FF
            0x9A,              # TXS
            0xE8,              # INX -> 0
            0x8E, 0x00, 0x20,  # STX $2000
            0x8E, 0x01, 0x20,  # STX $2001
            0x4C, 0x11, 0x80,  # JMP $8011
        ]
    )
    prg[: len(program)] = program
    for offset in (0x3FFA, 0x3FFC, 0x3FFE):
        prg[offset : offset + 2] = b"\x00\x80"
    chr_rom = bytes(8 * 1024)
    return header + bytes(prg) + chr_rom


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("refusing to overwrite {}".format(args.output))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(build_rom())
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
