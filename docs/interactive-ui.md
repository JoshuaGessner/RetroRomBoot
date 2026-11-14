# The interactive UI (`romboot ui`)

RomBoot ships a guided terminal menu that ties every host-side feature —
host checks, ROM inspection, image preparation, verification, and flashing —
into one flow. It is a convenience front-end: every action calls the same
functions as the individual `romboot` subcommands, so the security, staging,
and flash safeguards are identical. Nothing is bypassed.

The UI uses only the Python standard library, so it runs anywhere the CLI
runs — no extra install.

## Launching it

Any of these open the menu:

```sh
romboot            # bare command, no subcommand -> UI
romboot ui         # explicit
python3 -m romboot # if you have not `pip install -e .`
```

Optional flags let the UI compile images without prompting for paths:

```sh
romboot ui --buildroot-dir /path/to/buildroot-2025.02.16 \
           --output ./artifacts --jobs 6
```

`--buildroot-dir` can also come from the `BUILDROOT_DIR` environment variable.

## The home screen

```text
  RomBoot  —  build a one-game console image
  ──────────────────────────────────────────────────────────
  host: Python ok  platform ok  make ok  zstd ok  Buildroot warn

   1) Build an appliance image   (pick console + ROM)
   2) Inspect a ROM
   3) Verify an image
   4) Flash an image to SD   (destructive)
   5) List consoles & targets
   6) Host check (doctor)
   q) Quit

  Choose [1] >
```

The `host:` line is a live summary of the same checks `romboot doctor` runs.
`ok` is green, a non-essential gap (`warn`) is yellow, and a missing essential
(`MISS`) is red. `Buildroot warn` simply means no Buildroot checkout is
configured on this host — you can still prepare staging trees; you just cannot
compile a bootable image here (see [Build](#1-build-an-appliance-image)).

### Keys and conventions

- A value in `[brackets]` is the default — press **Enter** to accept it.
- Where a prompt says *"blank to cancel"*, pressing **Enter** returns to the menu.
- Numbered lists: type the number and Enter.
- `q` (or Ctrl-D / end of input) quits.
- Colour turns off automatically when output is piped, or if you set
  `NO_COLOR=1`.

## 1) Build an appliance image

The wizard walks you through, in order:

1. **ROM file** — the path to your legally obtained game.
2. **Console** — auto-detected from the file extension. If detection is
   ambiguous or unknown, it asks you to choose from the console list.
3. **Target board** — `rpizero2w`, `rpi4`, … (only boards the console supports).
4. **Save behaviour** — `persistent` (battery saves written to the data
   partition), `ephemeral` (saves kept only until power-off), or `disabled`.
5. **Custom boot splash** — optional PNG; the default is the project's generic
   splash.

It then prints a summary and, on confirmation, **prepares the staging tree**
and verifies it structurally. This step works on any host (macOS, Linux,
Windows) and writes nothing outside the workspace under `build/`.

### Compiling the bootable image

Turning staging into a flashable `.img`/`.img.zst` is a Buildroot cross-compile
that needs a Linux Buildroot checkout:

- **If a Buildroot checkout is configured** (`--buildroot-dir` or
  `BUILDROOT_DIR`), the wizard offers to compile right away and prints the
  final image path, SHA-256, and manifest when done. This takes roughly
  20–60 minutes and adds more the first time cores are built.
- **If not** (typical on macOS), the wizard stops after preparing staging and
  prints the exact `romboot build … --buildroot-dir … --output …` command to
  run inside your Linux or Docker build environment. See
  [Building on Linux or in a container](building.md).

## 2) Inspect a ROM

Detects the console for a ROM and prints its details — platform, core, file
name, size, SHA-256, and any required BIOS — **without executing it**. Handy
for confirming a file is recognised before building.

## 3) Verify an image

Point it at any of:

- a **staging directory** (checked against its manifest),
- a **raw SD-card image** (`.img` — partition-table check), or
- a **packaged RomBoot artifact** (manifest + checksum sidecars).

For a file it asks which of the last two it is. This is the same logic as
`romboot verify [--raw]`.

## 4) Flash an image to SD (destructive)

This **erases the entire target device**, so it is deliberately cautious:

1. Enter the image file, then the whole-device path under `/dev`
   (e.g. `/dev/disk4` on macOS, `/dev/sdX` on Linux — not a partition).
2. The device is inspected and must be **removable/external** and large enough;
   the summary (model, size) is shown.
3. You are offered a **dry run** first (nothing written).
4. To write for real you must type the exact phrase `ERASE /dev/…`.

Notes:

- Writing to a raw device usually needs elevated privileges. If the write
  fails with a permission error, re-run the UI with `sudo`.
- The guarded flasher only accepts **packaged RomBoot artifacts** (those built
  with manifest/checksum sidecars). A bare `.img` from a container build has no
  sidecars — flash those with Raspberry Pi Imager (custom image) or
  `sudo dd if=<image> of=/dev/DEVICE bs=4m`. The wizard tells you this if it
  applies. See [Safe flashing](flashing.md).

## 5) List consoles & targets

Prints the registry: every console `id`, its status, supported target boards,
and full name — the same table as `romboot platforms`. BIOS-free consoles need
no extra files; `registry-proof-only` entries are not buildable yet.

## 6) Host check (doctor)

The full `romboot doctor` report: Python version, platform registry, `make`,
`zstd`, and whether a Buildroot source is configured. A clean report does not
prove physical Raspberry Pi compatibility — only a real boot does.

## Worked example: a SNES appliance

```text
Choose > 1                       # Build
ROM file > ~/roms/mygame.sfc
✓ Console: Super Nintendo… (snes, core snes9x2010)
Target board > 1                 # rpizero2w
Save behaviour > 1               # persistent
Add a custom boot splash PNG? (y/N) >   (Enter = no)
Prepare the staging tree now? (Y/n) >   (Enter = yes)
✓ Prepared snes at …/build/mygame-rpizero2w
✓ Staging verification passed.
```

With `BUILDROOT_DIR` set it then offers to compile; otherwise it prints the
`romboot build` command to finish in your Linux/Docker environment. After you
have a packaged artifact, return to the menu and choose **Flash**.

> RomBoot is one game per image. Building a SNES image does not remove your NES
> image — each ROM produces its own SD card.
