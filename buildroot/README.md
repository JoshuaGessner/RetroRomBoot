# RomBoot Buildroot external tree

This directory is a Buildroot `BR2_EXTERNAL` tree for a Raspberry Pi 4
appliance image.  It intentionally contains no ROMs, BIOS files, or
manufacturer assets.  The host-side `romboot build` workflow is responsible
for staging one validated ROM at `/rom/game.nes` and, where needed, validated
BIOS files before the final root filesystem is assembled.

The initial target uses musl, the cut-down Pi 4 boot firmware without unused DT overlays, a SquashFS root mounted read-only, and a small ext4 `ROMBOOT-DATA` partition for saves and bounded logs. `board/romboot/rpi4` contains the image layout and Raspberry Pi firmware configuration; the common rootfs overlay supplies the init scripts and runtime supervisor.

The tested source target is Buildroot 2025.02.16 LTS, pinned in the top-level
`dependencies.lock.json`. Verify its detached OpenPGP signature before use.
