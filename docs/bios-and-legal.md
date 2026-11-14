# BIOS and legal requirements

## User-supplied content only

RomBoot is an image builder, not a source of game content. Users must provide and have the right to use each ROM, disc image, BIOS, key, firmware, splash asset, font, and artwork. The project must not:

- download, package, commit, or distribute proprietary ROMs, BIOSes, firmware, keys, or copyrighted console boot animations;
- bypass DRM, encryption, or console security;
- transmit or retain user content outside the local build unless a user explicitly introduces a separate service;
- imply affiliation with console makers.

Only project-owned or clearly redistributable default art belongs in the repository. Third-party emulator/core and library licenses must be recorded in the generated license bundle; a core may not be redistributed merely because it is technically buildable.

## BIOS workflow

NES does not normally need a BIOS and is the initial end-to-end platform. BIOS-dependent platforms will declare their requirements in the platform registry. A definition distinguishes required from optional files and states the expected destination for its selected emulator/core.

Planned example:

```sh
romboot build \
  --rom /path/to/game.cue \
  --platform ps1 \
  --target rpi4 \
  --bios-dir /path/to/my-legally-obtained-bios \
  --output game.img.zst
```

The tool should accept individual `--bios` paths as well as `--bios-dir`. It validates the filename, size, and cryptographic digest when an authoritative expectation is documented. A filename alone is never considered a valid BIOS. The build fails clearly if a required file is missing or mismatched, and it copies only BIOS files necessary for the configured platform/core.

The generated manifest records BIOS **filenames and hashes**, not their contents. It should avoid source paths unless explicitly requested. BIOS fixtures must never be committed to source control or CI.

## ROM and archive safety

ROMs and associated assets are untrusted inputs. The host tool must reject path traversal, symlink escapes, device files, unsafe output/input collisions, and unsafe archive members. Archive support, when available, enforces decompressed-size and entry-count limits, rejects links and paths outside the staging root, and refuses ambiguous archives until the user chooses a game. Disc sets (for example CUE/BIN, CHD, M3U) require all referenced files to validate as one set.

RomBoot does not execute or emulate a ROM during inspection; `inspect` only examines file metadata and permitted signatures.
