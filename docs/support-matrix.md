# Platform and Raspberry Pi support matrix

Status labels are intentionally strict:

- **MVP structural** — host implementation and image profile exist; a complete Buildroot build and physical-hardware result are still required.
- **Registry planned** — data model is designed for it; it is not a claim of working build/runtime support.
- **Future investigation** — no compatibility promise.

## Raspberry Pi targets

| Target ID | Hardware | Status | Notes |
| --- | --- | --- | --- |
| `rpi4` | Raspberry Pi 4 Model B | MVP structural | Buildroot image profile exists. HDMI, input, audio, firmware, and boot behavior require physical validation. |
| `rpi3` | Raspberry Pi 3 | Future investigation | Separate target profile and performance testing required. |
| `rpizero2w` | Raspberry Pi Zero 2 W | MVP structural | Dedicated Buildroot profile exists; boot, VideoCore IV, mini-HDMI audio/video, OTG input, and performance require physical validation. |
| `rpi5` | Raspberry Pi 5 | Future investigation | Separate firmware, driver, and emulator testing required. |

## Console platforms

| Tier | Platform IDs / examples | Status | BIOS expectation |
| --- | --- | --- | --- |
| 1 | `nes`, `snes`, `gb`, `gba`, `sms`, `gamegear`, `genesis`, `pcengine` | MVP structural | BIOS-free cartridge/handheld configurations; CD add-ons are excluded |
| 1 | Atari 2600 and other BIOS-free cartridge systems | Registry planned | Platform-specific |
| 2 | `psx` / PlayStation 1 | Registry proof only | BIOS metadata is modeled, but hashes, disc-set validation, emulator packaging, image builds, and hardware support remain disabled |
| 3 | Nintendo 64, Dreamcast, PSP, other performance-sensitive systems | Future investigation | Varies; support is contingent on board and emulator testing |

Each registry entry is expected to contain a stable identifier, aliases, accepted extensions, archive policy, core choices, BIOS requirements/digests/paths, video and input defaults, save behavior, supported targets, licensing restrictions, and limitations. A registry entry by itself does not mean an image has been tested on hardware.
