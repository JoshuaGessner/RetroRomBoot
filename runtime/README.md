# RomBoot runtime contract

The current production-oriented runtime is installed by the Buildroot overlay
at `buildroot/board/romboot/common/rootfs-overlay`.  This directory documents
the stable contract consumed by host image builders while avoiding a second,
divergent copy of init scripts.

Before rootfs assembly, the host builder must install exactly one selected ROM
under `/rom` and replace `/etc/romboot/game.env`.  It must reject newlines,
shell metacharacters, and non-absolute paths in all generated assignments.  In
the initial NES target the expected fields are:

- `ROMBOOT_EMULATOR`: absolute emulator path.
- `ROMBOOT_CORE`: absolute libretro core path.
- `ROMBOOT_ROM`: absolute staged ROM path.
- `ROMBOOT_RETROARCH_CONFIG`: absolute RetroArch configuration path.
- `ROMBOOT_SPLASH`: absolute generic or user-supplied splash path.
- `ROMBOOT_EXIT_POLICY`: `shutdown`, `restart-once`, or `error`.

Release images mount `/` read-only.  `/data` is the sole writable partition;
`/data/saves` and `/data/logs` are created by `S20romboot-data` before
`S90romboot` starts the supervisor.  The supervisor automatically powers off
after the game exits, so RetroArch's configured exit hotkey doubles as the
safe shutdown control in this initial appliance flow.
