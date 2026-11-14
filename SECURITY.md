# Security policy

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting feature for this repository when available. Do not open a public issue for a flaw that could cause arbitrary code execution, expose uploaded game/BIOS content, bypass archive or path validation, or write to the wrong block device.

Include a concise reproduction, affected version or commit, impact, and any suggested mitigation. Never include copyrighted ROM or BIOS content in a report.

## Security boundaries

RetroRomBoot treats ROMs, archives, BIOS files, splash images, filenames, web uploads, manifests, and device paths as untrusted input. The self-hosted web UI is designed for a single trusted operator and binds to localhost by default; it is not a public ROM hosting service. Set a strong `ROMBOOT_WEB_TOKEN` and add transport security before deliberately exposing it beyond localhost.

Flashing is intentionally conservative and destructive by nature. Always verify the selected whole removable device, image checksum, and displayed capacity before confirming a write. No software safeguard replaces operator review.

Only the latest revision on the default branch is supported until versioned releases begin.
