# ADR 001: Build a minimal appliance image with Buildroot

- Status: accepted for the initial MVP
- Date: 2026-07-23

## Context

RomBoot must generate a small, reproducible Raspberry Pi image that directly runs one game. It needs a cross toolchain, kernel/firmware integration, a restricted target root filesystem, emulator packaging, image generation, and licensing metadata without a package manager or desktop on the target.

## Decision

Use a pinned Buildroot release plus a RomBoot external tree for Raspberry Pi target configuration, runtime overlay, package definitions, hashes, and image layout. The host-facing `romboot` command is zero-dependency Python 3.11+; it orchestrates validation, staging, Buildroot, image assembly, manifests, and verification. It is not part of the target operating system.

The production design uses a small FAT boot partition, a read-only root filesystem (prefer SquashFS where the emulator stack permits it), `tmpfs` for transient state, and an optional small writable data partition for persistent saves. Release images omit package management, compilers, development headers, desktop stacks, SSH, and unnecessary network services.

## Considered options

| Option | Benefits | Why not selected for the MVP |
| --- | --- | --- |
| **Buildroot** | Purpose-built for embedded cross builds; can generate toolchain, kernel, boot assets, and root filesystem; supports external trees, offline builds, SBOM generation, and filesystem-size analysis. | Selected. It requires disciplined package/version pinning and a Linux-oriented build environment. |
| Yocto / OpenEmbedded | Strong metadata model and excellent fit for large multi-product distributions. | More setup and maintenance weight than a single-purpose image generator needs initially; longer feedback cycle for this MVP. Revisit if layers, board variants, or commercial lifecycle demands grow substantially. |
| Minimised Debian / Raspberry Pi OS | Broad binary package availability and familiar administration. | A general-purpose, writable distribution conflicts with the smallest appliance image and increases unwanted services, update surface, and reproducibility work. |
| Alpine Linux | Small base and security-conscious defaults. | A package-distribution base still requires Pi-specific integration and strict removal of general-purpose services; emulator availability/compatibility and system integration need validation. |
| Custom initramfs-only system | Potentially the smallest runtime and no root filesystem writes. | Poorer fit for emulator libraries, persistent optional saves, diagnostics, upgrades, and multi-console expansion. It may become an optimization for a narrowly constrained target later. |

Buildroot documents that it automates complete embedded Linux generation via cross compilation, including a toolchain, root filesystem, Linux kernel, and bootloader; it also documents external customizations, offline builds, SBOM support, and filesystem-size analysis. [Buildroot manual](https://buildroot.org/downloads/manual/manual.html) is the primary implementation reference. The [Yocto quick-build documentation](https://docs.yoctoproject.org/brief-yoctoprojectqs/index.html) informs the alternative assessment.

## Consequences

Positive:

- A target has only the components explicitly selected.
- Host builds are unprivileged except for the separately guarded flash operation.
- Board and platform definitions can stay data-driven around a stable appliance runtime.
- Build inputs and output partition layout can be controlled for reproducibility.

Costs and limits:

- Linux is the primary build host. macOS and Windows need a Linux VM/container/WSL2 workflow.
- Emulator/core packaging must be reviewed individually for license and redistribution terms.
- A Buildroot upgrade is an intentional, tested dependency change rather than a casual package update.
- Buildroot output directories are build artifacts, not target filesystems to copy directly.

## Revisit when

Reconsider this decision if evidence shows Buildroot cannot support a required Raspberry Pi/emulator combination, if an authoritative emulator dependency requires a different base, or if multi-product lifecycle management makes a Yocto layer model materially more valuable than a focused appliance build.
