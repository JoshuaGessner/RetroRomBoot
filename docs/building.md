# Building an image

RomBoot separates untrusted game input from the Linux cross-build. It never downloads ROMs or BIOS files. Use only files you are legally permitted to use.

## Native Linux build

Install Python 3.11+, GNU Make, the standard Buildroot host prerequisites, and `zstd` when producing a compressed artifact. Obtain Buildroot 2025.02.16 from the URL in `dependencies.lock.json`, verify its detached OpenPGP signature with a trusted Buildroot release key, and extract it outside this repository.

```sh
python3 -m pip install -e .

romboot build \
  --rom /absolute/path/game.nes \
  --platform nes \
  --target rpi4 \
  --buildroot-dir /absolute/path/buildroot-2025.02.16 \
  --workspace build/game-rpi4 \
  --output images/game.img.zst \
  --jobs 6

romboot verify images/game.img.zst
```

The output is accompanied by `.sha256`, `.manifest.json`, and `.licenses/` sidecars. RomBoot refuses to overwrite any of them. Use a fresh output name or deliberately archive the earlier build.

For a raw, unpackaged Buildroot image during development:

```sh
romboot verify --raw build/game-rpi4/buildroot-output/images/sdcard.img
```

## Linux container build environment

The pinned container is useful on macOS or on Linux hosts where Buildroot dependencies should remain isolated. Docker still runs a Linux Buildroot build; it does not make physical Raspberry Pi behavior testable on the host. On Docker Desktop, keep the Buildroot output on a Docker-managed Linux volume: a macOS bind mount can break concurrent source extraction semantics.

```sh
docker build -t romboot-buildroot:2025.02.16 \
  -f containers/buildroot.Dockerfile .

# First prepare and validate exactly one ROM without executing it.
python3 -m romboot build \
  --rom /absolute/path/game.nes \
  --platform nes \
  --target rpi4 \
  --workspace /absolute/path/romboot-staging \
  --prepare-only

# The named volume is the Linux-native Buildroot work/output directory.
docker volume create romboot-build-output
docker run --rm --user 0:0 \
  -v romboot-build-output:/output \
  romboot-buildroot:2025.02.16 \
  chown -R "$(id -u):$(id -g)" /output

docker run --rm \
  --user "$(id -u):$(id -g)" \
  -e ROMBOOT_STAGING_ROOT=/staging/rootfs \
  -e SOURCE_DATE_EPOCH=0 \
  -v /absolute/path/buildroot-2025.02.16:/buildroot:ro \
  -v romboot-build-output:/output \
  -v /absolute/path/romboot-staging:/staging:ro \
  -v "$PWD":/romboot:ro \
  romboot-buildroot:2025.02.16 \
  make -C /buildroot O=/output BR2_DL_DIR=/output/dl \
    BR2_EXTERNAL=/romboot/buildroot romboot_rpi4_defconfig

docker run --rm \
  --user "$(id -u):$(id -g)" \
  -e ROMBOOT_STAGING_ROOT=/staging/rootfs \
  -e SOURCE_DATE_EPOCH=0 \
  -v /absolute/path/buildroot-2025.02.16:/buildroot:ro \
  -v romboot-build-output:/output \
  -v /absolute/path/romboot-staging:/staging:ro \
  -v "$PWD":/romboot:ro \
  romboot-buildroot:2025.02.16 \
  make -C /buildroot O=/output BR2_DL_DIR=/output/dl \
    BR2_EXTERNAL=/romboot/buildroot -j6

# Run legal-info before distributing, then export and verify the raw image.
docker run --rm \
  --user "$(id -u):$(id -g)" \
  -e ROMBOOT_STAGING_ROOT=/staging/rootfs \
  -v /absolute/path/buildroot-2025.02.16:/buildroot:ro \
  -v romboot-build-output:/output \
  -v /absolute/path/romboot-staging:/staging:ro \
  -v "$PWD":/romboot:ro \
  romboot-buildroot:2025.02.16 \
  make -C /buildroot O=/output BR2_DL_DIR=/output/dl \
    BR2_EXTERNAL=/romboot/buildroot legal-info

mkdir -p /absolute/path/romboot-artifacts
docker run --rm \
  -v romboot-build-output:/output:ro \
  -v /absolute/path/romboot-artifacts:/artifacts \
  romboot-buildroot:2025.02.16 \
  cp /output/images/sdcard.img /artifacts/sdcard.img

python3 -m romboot verify --raw /absolute/path/romboot-artifacts/sdcard.img
```

The native `romboot build` command performs `legal-info`, compression/copying, hashing, manifest creation, and complete release-sidecar packaging automatically.

Use a fresh, uniquely named output volume for each game/build. After exporting all required artifacts and license data, remove that exact volume deliberately with `docker volume rm`; never reuse an old volume for a different ROM.

## Custom splash and saves

Pass `--splash /path/to/asset.png` to compile a legally usable PNG into the early boot splash. Without it, RomBoot uses the generic project-owned splash.

Select `--save-mode persistent`, `ephemeral`, or `disabled`. Persistent mode stores saves on the small data partition; ephemeral mode stores them in RAM; disabled mode discards them.

## Evidence boundary

A successful build and `verify` prove artifact structure and recorded hashes. They do not prove firmware, HDMI, audio, graphics, controller, game compatibility, or safe power behavior. Complete the physical checklist in `verification.md` on the exact Raspberry Pi and peripherals before making those claims.
