# RomBoot as a Docker web appliance

RomBoot's primary distribution is a single Docker container with a browser UI.
You run the container on any machine that has Docker — Linux, macOS, or Windows
— open a web page, upload one legally obtained ROM, and download a bootable
Raspberry Pi image. The container carries the whole Buildroot cross-compile
toolchain, so nobody needs to install Buildroot, a toolchain, or the CLI.

Flashing is intentionally **not** part of the service: it hands you a finished
image file and you write it to an SD card with your own tool (Raspberry Pi
Imager, balenaEtcher, or `dd`). See [Why no flashing](#why-no-flashing).

## Quick start

```sh
docker compose up --build
# then open http://localhost:8080
```

That builds the image (a few minutes: apt packages + a pinned Buildroot
checkout) and starts the service. The web page walks you through:

1. **ROM file** — drop in your game; the console is auto-detected and inspected
   (name, core, size, SHA-256, any required BIOS) without ever executing it.
2. **Target board** — only the boards the detected console supports.
3. **Save behaviour** — persistent, ephemeral, or disabled.
4. **Custom boot splash** — optional PNG.
5. **Build image** — watch the live build log, then **Download** the artifact.

The **first** build for a given board compiles the cross-toolchain, kernel,
RetroArch, and cores — roughly 30–60 minutes. Every build after that reuses the
warm cache and finishes in minutes (see [Fast rebuilds](#fast-rebuilds-and-file-safety)).

## What runs where

```
Browser ──upload ROM · start build · stream logs (SSE)──▶  container :8080
   ▲                                                          │
   └───────────────── download .img.zst ─────────────────────┘

Container:  stdlib web server  ─▶  build-job queue (one at a time)
            ─▶  romboot CLI core (unchanged)  ─▶  Buildroot + toolchain

Volumes:    /data   uploads, per-build workspaces, logs, artifacts
            /cache  warm per-target Buildroot output + shared download cache
```

The web layer only calls the same `romboot` functions the command line uses —
nothing is bypassed. It depends on the Python standard library alone, so the
whole project stays dependency-free.

## Configuration

All settings are environment variables (see `docker-compose.yml`):

| Variable | Default | Purpose |
| --- | --- | --- |
| `ROMBOOT_WEB_HOST` | `0.0.0.0` (in the image) | Address the container binds. Keep the *host* publish on `127.0.0.1` in compose. |
| `ROMBOOT_WEB_PORT` | `8080` | Listen port. |
| `ROMBOOT_WEB_JOBS` | CPU count | `make -jN` parallelism per build. |
| `ROMBOOT_WEB_TOKEN` | unset | If set, every request must carry it (`X-RomBoot-Token` header or `?token=`). Required before exposing beyond localhost. |
| `ROMBOOT_WEB_MAX_UPLOAD` | `4294967296` | Max single-upload size in bytes. |
| `ROMBOOT_WEB_OUTPUT_SUFFIX` | `.img.zst` | `.img.zst` (smaller download) or `.img` (raw). |
| `ROMBOOT_WEB_DATA` | `/data` | Mutable per-run state. |
| `ROMBOOT_WEB_CACHE` | `/cache` | Reused Buildroot output + downloads. |
| `BUILDROOT_DIR` | `/opt/buildroot` | Pinned Buildroot source (baked into the image). |

## Security and legal posture

RomBoot never downloads, includes, or distributes ROMs, BIOS files, keys, or
firmware — and this service keeps that intact. **It is a self-hosted,
single-tenant tool, not a public upload site.** Running it as an open service
that accepts strangers' uploads would turn it into exactly the kind of
ROM-distribution service RomBoot refuses to be.

- The compose file publishes the port to `127.0.0.1` only. To reach it from
  another machine, set `ROMBOOT_WEB_TOKEN` **and** change the publish address
  deliberately.
- Uploads are size-limited, filename-sanitised, stored outside any executable
  path, and never run. Detection reads headers and hashes only.
- Builds run one at a time as an unprivileged user; the warm cache lives on a
  volume, so the container stays disposable.

## Fast rebuilds and file safety

The expensive part of a build — the toolchain and all packages — is independent
of which game you selected. RomBoot keeps a **warm per-target Buildroot output**
in the `/cache` volume and reuses it, so only the game-specific rootfs is
regenerated on repeat builds.

Reuse is made safe against leftover files two ways:

- **An install ledger.** `post-build.sh` records every file each build stages
  (ROM, BIOS, splash, `game.env`) and deletes the previous build's exact set
  before applying the new one — so a reused tree can never keep another game's
  content, wherever it landed.
- **A forced splash rebuild.** The boot splash is compiled into the `psplash`
  package, not merely copied, so a reused tree rebuilds `psplash` each time to
  match the current build's splash.

Builds are serialized (one at a time), so two builds never touch the same warm
cache concurrently. Different boards use separate warm trees under
`/cache/build/<target>`; the download cache in `/cache/dl` is shared.

## Why no flashing

Flashing writes raw bytes to a physical SD card device. Docker Desktop on macOS
and Windows runs containers in a Linux VM that does not expose the host's USB
card reader, and even on Linux it needs privileged device mapping. Rather than a
fragile, platform-specific flash button, the service hands back the finished
image and shows you how to write it:

- **Raspberry Pi Imager** → *Use custom image*. If the file ends in `.zst`,
  decompress first: `zstd -d game-rpizero2w.img.zst`.
- **Linux / macOS:**

  ```sh
  zstd -d game-rpizero2w.img.zst
  sudo dd if=game-rpizero2w.img of=/dev/YOUR_SD_DEVICE bs=4M conv=fsync
  ```

Verify the download against the SHA-256 shown next to the download button first.
RomBoot builds one game per card.

## Running without Docker

The web layer is stdlib-only, so you can also run it directly on a Linux host
that has the Buildroot prerequisites and a pinned Buildroot checkout:

```sh
BUILDROOT_DIR=/path/to/buildroot-2025.02.16 \
ROMBOOT_WEB_DATA=./data ROMBOOT_WEB_CACHE=./cache \
python3 -m romboot_web
```

The command line (`romboot build …`) remains available for scripted or
air-gapped builds; see [building](building.md).
