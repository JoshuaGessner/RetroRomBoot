# Verification status and hardware checklist

## Status discipline

RomBoot uses three distinct evidence levels:

| Level | Can establish | Cannot establish |
| --- | --- | --- |
| Unit/integration test | Input handling, configuration, manifest content, image structure, expected files | Raspberry Pi firmware, HDMI, GPU, audio, USB input, actual gameplay |
| QEMU/emulation check | Limited kernel/userspace behavior where modeled | Real Pi boot firmware, hardware-specific graphics/audio/input, SD-card reliability |
| Physical hardware test | Observed behavior on the stated board/peripherals | Compatibility with untested boards, displays, controllers, games, or power conditions |

At this documentation revision, no physical Raspberry Pi boot result is asserted. The MVP is complete only after its required structural tests pass **and** a real Raspberry Pi 4 test records results honestly.

## Required structural checks

- Build a legal, redistributable NES test ROM image.
- Inspect the partition table and mount/extract filesystems without booting.
- Confirm there is exactly one selected ROM and no unrequested BIOS.
- Confirm runtime configuration names the intended ROM and core.
- Confirm release configuration has no desktop, login prompt, SSH service, package manager, or unnecessary network service.
- Verify manifest and compressed-image checksums.
- Test secure paths, archive limits, ambiguous detection, BIOS error reporting, save-mode configuration, and flash-device safeguards.
- Rebuild with pinned inputs and record whether output is bit-for-bit identical or why it is not.

## Raspberry Pi 4 manual checklist

Record the exact board revision, SD-card model/capacity, display, HDMI path, controller/keyboard, core/version, and test game. Mark pass, fail, or not tested for each:

- [ ] Cold boot reaches splash then game.
- [ ] No unintended rainbow screen, console text, cursor, login prompt, desktop, or launcher is visible.
- [ ] No prolonged blank or disruptive display-mode transition occurs.
- [ ] USB controller is detected and keyboard fallback works.
- [ ] Video mode, aspect ratio, integer scaling, and overscan behavior are correct.
- [ ] HDMI audio works; no-audio behavior is understandable.
- [ ] The correct game auto-launches and accepts input.
- [ ] Persistent saves survive a safe reboot; ephemeral and disabled modes behave as configured.
- [ ] Reset, quit, and shutdown chords are intentional and distinct.
- [ ] Safe shutdown flushes data and powers down predictably.
- [ ] Emulator exit/crash behavior follows the selected bounded policy; no restart loop or shell appears.
- [ ] Repeated cold boots remain reliable.
- [ ] A controlled power-loss test has a documented outcome and the read-only/persistent-data design recovers appropriately.

Never convert an unchecked item into a compatibility claim. QEMU can assist early development, but it does not substitute for this list.
