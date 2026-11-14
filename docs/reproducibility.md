# Reproducibility and supply chain

RomBoot aims for auditable image creation, not opaque “latest” builds. Every source dependency, Buildroot release, package patch, toolchain input, emulator/core, and container base (when used) must be pinned by version plus immutable revision and/or checksum where available. The build must not execute remote scripts through a shell pipeline.

The current lock selects Buildroot 2025.02.16 LTS, RetroArch 1.21.0, and an immutable FCEUmm commit. The Raspberry Pi 4 target kernel is the pinned `raspberrypi/linux` fork commit `576cc10e1ed50a9eacffc7a05c796051d7343ea4` (rpi-6.6.y, SHA-256 recorded in `dependencies.lock.json`) — the same commit Buildroot 2025.02.16 ships in `raspberrypi4_64_defconfig`; mainline lacks `bcm2711_defconfig` and cannot mount the XZ squashfs root, and the toolchain kernel headers are pinned to 6.6 to match. Git-generated source archives and license files have SHA-256 entries in the external package metadata. The Linux build container is pinned by image digest in `containers/buildroot.Dockerfile`; `dependencies.lock.json` is the human- and machine-readable source record.

## Build record

Each completed image has an adjacent manifest, checksum, Buildroot `legal-info` bundle, and verified partition report. The manifest currently records:

- RomBoot version/source revision and reproducible-build epoch or build timestamp;
- target ID, platform, selected emulator/core, and component versions;
- ROM filename stored in the image and its cryptographic digest;
- BIOS filenames and digests, never their content;
- user-supplied asset digests;
- effective configuration and partition layout;
- compressed artifact size, uncompressed image size, and partition extents;
- dependency/license summary; and
- whether the exact build is expected to reproduce bit-for-bit.

Do not expose local source paths by default, and never print ROM or BIOS content in logs.

## Repeatability rules

- `SOURCE_DATE_EPOCH`, deterministic file ordering, and stable image metadata should be used where component support permits.
- Downloads are verified before use; after a dependency cache is populated, offline rebuilds should be possible.
- Cache artifacts must be content-addressed or otherwise verified so a cache cannot silently change output.
- Source acquisition and image assembly should be separable.
- An SBOM should be produced when the selected Buildroot release/package set supports it.
- Rebuild tests compare relevant artifacts and explain known nondeterminism instead of overstating bit-for-bit reproducibility.

## Size accounting

Image size is a product requirement. The current manifest reports total artifact and partition sizes. Before a release, the size report must additionally split the boot partition, root filesystem, writable data partition, kernel/modules, firmware, emulator/core, shared libraries, ROM/BIOS, spare space, and compressed output. Once a measured baseline exists, CI should flag a meaningful unexplained increase.

Size optimization must not remove essential firmware, license notices, or required source-offer material. Debug symbols belong in a separate artifact where appropriate, not in a normal appliance image.
