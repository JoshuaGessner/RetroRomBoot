# Expansion research: more Raspberry Pi boards, emulation up to the PS2 era

Scope: what it takes to grow RomBoot beyond its current `{rpi4, rpizero2w}` targets
and NES-only platform toward more Raspberry Pi boards and more consoles, up to the
PS2 era. Everything is framed in RomBoot's existing model: a declarative platform
entry (`platforms/*.json`) + a pinned libretro-core Buildroot package + an optional
BIOS spec, and a per-board target (`targets/*.toml` + a defconfig + `board/romboot/<id>/`).

This is a planning document, not a compatibility claim. Nothing here is validated on
hardware; per `docs/verification.md`, each board+core+game combination needs its own
physical test.

## 1. Raspberry Pi hardware tiers

| Board(s) | SoC / CPU | GPU (mesa) | RAM | Arch | RomBoot status | Realistic emulation ceiling |
|---|---|---|---|---|---|---|
| Zero / Zero W / 1 | BCM2835, ARM11 1-core ~1 GHz | VideoCore IV | 512 MB | ARMv6 (32-bit) | — | 8-bit + light 16-bit only. ARMv6 needs a different toolchain than our aarch64 — **skip.** |
| 2 | BCM2836, Cortex-A7 ×4 0.9 GHz | VC IV | 1 GB | ARMv7 (32-bit) | — | Full 8/16-bit + GBA. Different toolchain; low value. |
| **Zero 2 W** / 3 / 3A+/3B+ | BCM2837, Cortex-A53 ×4 1.0–1.4 GHz | VC IV, GLES2 (`vc4`) | 512 MB–1 GB | aarch64 | **Zero 2 W shipped** | 8/16-bit + GBA/PCE flawless; PS1 playable (pcsx-rearmed); N64/PSP marginal, case-by-case; no Saturn/Dreamcast. |
| **4** / 400 / CM4 | BCM2711, Cortex-A72 ×4 1.5–1.8 GHz | VideoCore VI, GLES3.1 + Vulkan (`v3d`) | 1–8 GB | aarch64 | **Pi 4 target exists** (unbuilt/partly-fixed) | Sweet spot for "up to ~2000": PS1 near-complete, N64 good, Dreamcast full (flycast/Vulkan), PSP good, Saturn provisional/heavy. **No PS2.** |
| 5 / 500 / CM5 | BCM2712, Cortex-A76 ×4 2.4 GHz | VideoCore VII, GLES3.1/Vulkan | 4–8 GB | aarch64 | — | ~3× CPU / 2.8× GPU vs Pi 4 → N64/Dreamcast/PSP full speed, Saturn good; **PS2 experimental/"spotty" only.** Needs active cooling (throttles 2.4→1.5 GHz). |

Architecture note: Zero 2 W / 3 / 4 / 5 are all **aarch64**, so they share the musl
aarch64 toolchain and nearly all of userland — only the *board layer* differs (CPU
tune, DTB, firmware variant, GPU driver, overlays, `config.txt`). That is exactly the
`rpizero2w` vs `rpi4` split we already have. Pi 0/1/2 are 32-bit ARMv6/v7 → separate
toolchain, not worth it.

**Pi 5 is the one big exception:** BCM2712 + the RP1 south-bridge is a substantially
different platform (firmware, DTBs, overlays, PCIe, V3D 7.1). Budget real bring-up, not
a copy of the rpi4 target.

## 2. Console → core → BIOS → feasible-Pi matrix

Recommended libretro cores, whether a user-supplied BIOS is required, and the minimum
Pi tier for a "playable" experience.

**8/16-bit — every aarch64 board, including the Zero 2 W:**

| System | Core(s) | BIOS | Notes |
|---|---|---|---|
| NES/Famicom | fceumm *(shipped)* / nestopia / mesen | no | — |
| SNES/SFC | snes9x2010 (fast) / snes9x / bsnes-mercury (accuracy, Pi 4+) | no | — |
| Genesis/MD, SMS, GG, SG-1000 | genesis-plus-gx / picodrive | no* | *Sega/Mega-CD needs BIOS |
| PC Engine / TG16 | beetle-pce-fast | no* | *CD variants need System Card |
| Game Boy / GBC | gambatte / sameboy | no | — |
| GBA | mgba (HLE) / vba-next | optional | — |
| Neo Geo | fbneo / geolith | **yes** (neogeo.zip) | — |
| Atari 2600/5200/7800/Lynx, WonderSwan, NGP | stella / a5200 / prosystem / handy / mednafen | mostly no | — |

**Early-3D / 32-bit era — Zero 2 W case-by-case, Pi 4 comfortable, Pi 5 easy:**

| System | Core(s) | BIOS | Min tier |
|---|---|---|---|
| PlayStation (PS1) | **pcsx-rearmed** (fast) / beetle-psx-hw (accurate, heavier) | **yes** (scph5501/1001/7001…) | Zero 2 W playable; Pi 4 excellent |
| Nintendo 64 | mupen64plus-next (GLideN64) / parallel-n64 | no | Pi 4 good; Pi 5 full; Zero 2 W/3 marginal |
| PSP | ppsspp | no | Pi 4 good; Pi 5 great; Zero 2 W/3 marginal |
| Sega Saturn | beetle-saturn (heavy) / kronos / yabause | **yes** | Pi 4 provisional/hard; Pi 5 good |
| Sega Dreamcast | flycast (Vulkan) | recommended (dc_boot/dc_flash) | Pi 4 full; Pi 5 great; beyond Zero 2 W/3 |

**The ceiling — PS2:** there is **no production-ready ARM libretro core**. AetherSX2 is
discontinued; Play! (`play`) is WIP; results are "spotty at best" even on Pi 5. Treat
PS2 as *experimental, Pi 5 only, do not promise it.* (For context, an RPCS3 arm64
build even runs some PS3 on Pi 5 — a curiosity, nowhere near appliance-grade.)

## 3. What each addition costs in RomBoot

**Per new console** (mostly data + one package):
- `platforms/<id>.json`: extensions, aliases, `emulator="retroarch"`, core id,
  `target_support`, BIOS spec (names, destination paths, documented digests),
  settings (aspect/region/scaling). RomBoot already data-drives and validates this.
- A pinned libretro-core package under `buildroot/package/romboot-libretro-<core>/`
  (mirror `romboot-libretro-fceumm`: git commit pin + hash + `.mk`), enabled in the
  relevant defconfig(s).
- BIOS: RomBoot already has `bios.py` / `resolve_bios` and the "only required BIOS
  reaches the image" invariant. A platform just declares its BIOS; the **user supplies
  the files** — RomBoot never ships or downloads BIOS/keys (the legal boundary holds).
  Update `docs/bios-and-legal.md`.
- Tests + fixtures (no copyrighted ROM/BIOS data) per `docs/extending-romboot.md`.

**Per new aarch64 board** (the `rpizero2w` pattern):
- `targets/<id>.toml` + registry `target_support` + `romboot_<id>_defconfig` +
  `board/romboot/<id>/{config.txt,cmdline.txt,genimage.cfg,post-image.sh}`.
- Reuse the shared `board/romboot/common/linux.fragment` (all the "must be built-in"
  fixes) and the common runtime overlay.
- Board-specific bits: CPU tune (a53/a72/a76), DTB name, `RPI_FIRMWARE` variant +
  `BOOTCODE_BIN` (Pi 0–3 boot `bootcode.bin` from SD; Pi 4/5 boot from EEPROM), GPU
  driver (`vc4` for Pi 0–3, `v3d` for Pi 4/5), overlays, HDMI connector name.
- **Pi 5**: a genuine port, not a copy — see §1.

## 4. Lessons from the Zero 2 W bring-up that carry to every new target/core

- **`=y` not `=m`.** With no initramfs, everything on the boot/probe path must be built
  into the kernel. We were bitten four times: SquashFS, DRM/VC4 (which silently caps at
  `=m` unless `SND=y`), the HDMI DDC `I2C_BCM2835`, and the `dwc2` USB controller. The
  shared `linux.fragment` encodes these; heavier targets/cores may need more (Vulkan/V3D
  for Dreamcast on Pi 4/5, extra USB/audio for peripherals). **Always verify a fragment
  symbol actually stuck `=y` after `make linux-reconfigure`.**
- **RAM.** The Zero 2 W's 512 MB caps PS1/N64/PSP; Pi 4 (2–8 GB) is the floor for the
  demanding tier. Larger cores → watch squashfs/boot-partition sizing.
- **GPU API.** Our `vc4` GLES2 path is fine through PS1/2D. N64/Dreamcast/PSP want
  GLES3/Vulkan → Pi 4 (`v3d`) or Pi 5.
- **Controllers.** We had to hand-map one gamepad by VID/PID. **Bundle
  `libretro/retroarch-joypad-autoconfig`** (a small data set + `joypad_autoconfig_dir`)
  to auto-configure most controllers — increasingly important as boards/consoles grow.
- **Per-core config.** Heavier cores need per-core options (renderer, threaded video,
  frameskip, BIOS paths). The single `retroarch.cfg` + `game.env` model likely needs a
  per-platform config overlay.
- **Thermals (Pi 5).** Sustained N64/PSP throttles without the active cooler — any
  appliance claim must document the cooling assumption.

## 5. Suggested roadmap (lowest effort / highest payoff first)

1. **Broaden cores on the boards we already have** (no new board): SNES, Genesis/SMS/GG,
   GB/GBC, GBA, PC Engine — all BIOS-free, all run great on Zero 2 W and Pi 4. Biggest
   catalog gain for the least risk; each is one core package + one platform JSON.
2. **Add the Pi 3 / 3B+ target** — trivial (same BCM2837 as the Zero 2 W; just the `PI`
   firmware variant, DTB name, and more RAM). A roomier 8/16-bit + PS1 box.
3. **Add PS1 (pcsx-rearmed)** — enormous library, playable on the Zero 2 W and excellent
   on Pi 4; exercises the BIOS flow properly.
4. **Finish the Pi 4 target, then N64 / PSP / Dreamcast on it.** Note the rpi4 defconfig
   still has the same *missing-overlays* bug the Zero 2 W had (`INSTALL_DTB_OVERLAYS`
   off, no overlays staged in genimage) plus it needs the `v3d`/GLES3/Vulkan display
   path validated — fix those first, mirroring `rpizero2w`.
5. **Pi 5 target** (larger bring-up) → Saturn + smoother N64/DC/PSP.
6. **PS2**: watch-and-wait. No appliance-grade ARM core exists today (Pi 5 experimental
   only). Don't advertise it.

## Sources
- [Raspberry Pi 5 game emulation tested — Geeky Gadgets](https://www.geeky-gadgets.com/raspberry-pi-5-game-emulation/)
- [Raspberry Pi 5 Recalbox emulation tested — Tom's Hardware](https://www.tomshardware.com/news/raspberry-pi-5-recalbox-emulation-tested)
- [Pi 5: N64 and Dreamcast at full speed — Botmonster](https://botmonster.com/self-hosting/build-retro-gaming-console-raspberry-pi-5-retropie/)
- [RPCS3 arm64 brings PS3 emulation to the Pi 5 — Notebookcheck](https://www.notebookcheck.net/RPCS3-arm64-build-brings-PS3-emulation-to-the-Raspberry-Pi-5.930789.0.html)
- [Raspberry Pi 4 and the state of video game emulation — Hackaday](https://hackaday.com/2020/01/14/raspberry-pi-4-and-the-state-of-video-game-emulation/)
- [Raspberry Pi 4 64-bit libretro cores — Raspberry Pi Forums](https://forums.raspberrypi.com/viewtopic.php?t=328242)
- [Raspberry Pi 4 and Saturn emulation — SegaSaturn.co.uk](https://segasaturngroup.proboards.com/thread/11398/raspberry-pi-4-saturn-emulation)
