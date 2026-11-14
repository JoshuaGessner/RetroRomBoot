# Contributing to RetroRomBoot

Thanks for helping improve RetroRomBoot. Contributions should preserve its core promise: one legally supplied game, one small appliance image, and no bundled copyrighted game or console content.

## Development setup

RomBoot's host tools require Python 3.9 or newer and have no runtime Python dependencies.

```sh
python3 -m pip install -e .
make check
```

Buildroot work additionally requires the pinned Buildroot release and Linux host prerequisites described in [docs/building.md](docs/building.md). A Buildroot configuration check is useful before opening a pull request; physical compatibility claims require the hardware checklist in [docs/verification.md](docs/verification.md).

## Pull requests

- Keep changes focused and explain the user-visible behavior.
- Add or update tests for host-side behavior.
- Update both `platforms/` and `romboot/data/platforms/` together.
- Pin every new downloaded source by immutable revision and checksum.
- Never commit ROMs, BIOS files, console firmware, keys, proprietary boot media, or copyrighted artwork.
- Do not claim hardware compatibility from configuration or emulation alone.
- Preserve the guarded flashing checks and the release image's no-login/no-network posture.

Run `make check` before submitting. If a change affects a target image, include the structural-build result and clearly state which physical checks were or were not performed.

## Reporting bugs

Include the host OS, Python/Docker version, target board, platform ID, command used, and sanitized error output. Do not attach copyrighted ROM or BIOS content; a filename, size, and SHA-256 digest are enough for identification.
