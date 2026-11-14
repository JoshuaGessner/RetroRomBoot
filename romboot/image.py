"""Buildroot execution, image packaging, and partition verification."""

import json
import os
import shutil
import struct
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from .builder import PreparedBuild
from .errors import RomBootError
from .manifest import load_manifest, write_manifest
from .security import require_regular_file, sha256_file

SUPPORTED_BUILDROOT_VERSION = "2025.02.16"


@dataclass(frozen=True)
class Partition:
    index: int
    type_code: int
    start_sector: int
    sector_count: int


@dataclass(frozen=True)
class BuiltImage:
    path: Path
    sha256: str
    manifest: Path


def run_buildroot(
    prepared: PreparedBuild,
    buildroot_source: Path,
    external_tree: Path,
    output: Path,
    jobs: int = 1,
    build_output: Optional[Path] = None,
    dl_dir: Optional[Path] = None,
) -> BuiltImage:
    source = buildroot_source.resolve()
    external = external_tree.resolve()
    if not (source / "Makefile").is_file():
        raise RomBootError("Buildroot source directory has no Makefile: {}".format(source))
    if not (external / "external.desc").is_file():
        raise RomBootError("invalid RomBoot Buildroot external tree: {}".format(external))
    if jobs < 1:
        raise RomBootError("jobs must be at least 1")
    output = output.resolve()
    sidecars = [
        output,
        output.with_name(output.name + ".sha256"),
        output.with_name(output.name + ".manifest.json"),
        output.with_name(output.name + ".licenses"),
    ]
    existing = [path for path in sidecars if path.exists()]
    if existing:
        raise RomBootError("refusing to overwrite output artifact: {}".format(existing[0]))
    # A caller may supply a warm, per-target Buildroot output directory that is
    # reused across builds so the cross-toolchain and packages are not rebuilt
    # every time.  When omitted, each build gets its own throwaway tree (the
    # original, always-clean behaviour).
    if build_output is None:
        build_output = prepared.directory / "buildroot-output"
    build_output = build_output.resolve()
    build_output.mkdir(parents=True, exist_ok=True)
    reused = (build_output / ".config").is_file()
    environment = dict(os.environ)
    environment["ROMBOOT_STAGING_ROOT"] = str(prepared.directory / "rootfs")
    environment.setdefault("SOURCE_DATE_EPOCH", "0")
    # post-build.sh reads this ledger to delete the previous build's staged
    # files (ROM, BIOS, splash, game.env) before applying this build's, so a
    # reused target directory can never retain another game's content.
    environment["ROMBOOT_INSTALL_LEDGER"] = str(build_output / ".romboot-install-ledger")
    common = [
        "make",
        "-C",
        str(source),
        "O=" + str(build_output),
        "BR2_EXTERNAL=" + str(external),
    ]
    if dl_dir is not None:
        dl_dir = dl_dir.resolve()
        dl_dir.mkdir(parents=True, exist_ok=True)
        common.append("BR2_DL_DIR=" + str(dl_dir))
    _run(common + ["romboot_{}_defconfig".format(prepared.target)], environment)
    _validate_buildroot_version(source)
    _configure_custom_splash(build_output, prepared)
    _run(common + ["olddefconfig"], environment)
    if reused:
        # The boot splash is compiled into the psplash package, not just copied
        # as a target file, so a reused tree would otherwise keep a prior build's
        # splash.  Force psplash to rebuild from this build's configuration.
        _run(common + ["psplash-dirclean"], environment)
    _run(common + ["-j{}".format(jobs)], environment)
    _run(common + ["legal-info"], environment)

    raw_image = build_output / "images" / "sdcard.img"
    if not raw_image.is_file():
        raise RomBootError("Buildroot completed without producing sdcard.img")
    structural = verify_raw_image(raw_image)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.suffix == ".zst":
        if shutil.which("zstd") is None:
            raise RomBootError("zstd is required for .zst output")
        _run(
            ["zstd", "--threads=0", "--no-progress", "-19", "-o", str(output), str(raw_image)],
            environment,
        )
    elif output.suffix == ".img":
        with raw_image.open("rb") as source_stream, output.open("xb") as output_stream:
            shutil.copyfileobj(source_stream, output_stream, 1024 * 1024)
    else:
        raise RomBootError("output must end in .img or .img.zst")

    digest = sha256_file(output)
    legal_info = build_output / "legal-info"
    if not legal_info.is_dir():
        raise RomBootError("Buildroot legal-info bundle was not produced")
    license_bundle = output.with_name(output.name + ".licenses")
    shutil.copytree(legal_info, license_bundle)
    checksum = output.with_name(output.name + ".sha256")
    checksum.write_text("{}  {}\n".format(digest, output.name), encoding="utf-8")
    source_manifest = load_manifest(prepared.manifest)
    source_manifest["licenses"] = {"directory": license_bundle.name}
    source_manifest["image"] = {
        "filename": output.name,
        "artifact_size": output.stat().st_size,
        "uncompressed_size": raw_image.stat().st_size,
        "compressed": output.suffix == ".zst",
        "sha256": digest,
        "partitions": [partition.__dict__ for partition in structural],
    }
    source_manifest["verification"]["structural"] = True
    artifact_manifest = output.with_name(output.name + ".manifest.json")
    write_manifest(artifact_manifest, source_manifest)
    return BuiltImage(output, digest, artifact_manifest)


def verify_raw_image(path: Path) -> List[Partition]:
    image = require_regular_file(path, "image")
    image_size = image.stat().st_size
    if image_size < 512:
        raise RomBootError("image is too small to contain an MBR")
    with image.open("rb") as stream:
        mbr = stream.read(512)
        if mbr[510:512] != b"\x55\xaa":
            raise RomBootError("image has no valid MBR signature")
        partitions: List[Partition] = []
        for index in range(4):
            entry = mbr[446 + index * 16 : 462 + index * 16]
            type_code = entry[4]
            start, count = struct.unpack_from("<II", entry, 8)
            if type_code and count:
                partitions.append(Partition(index + 1, type_code, start, count))
        if len(partitions) != 3:
            raise RomBootError("image must contain exactly three partitions")
        expected_types = [0x0C, 0x83, 0x83]
        if [item.type_code for item in partitions] != expected_types:
            raise RomBootError("unexpected partition types in image")
        previous_end = 0
        for item in partitions:
            start = item.start_sector * 512
            end = (item.start_sector + item.sector_count) * 512
            if start < previous_end or end > image_size:
                raise RomBootError("partition {} is out of bounds or overlaps".format(item.index))
            previous_end = end
        _verify_filesystem_magic(stream, partitions)
        return partitions


def verify_artifact(path: Path) -> None:
    artifact = require_regular_file(path, "artifact")
    checksum_path = artifact.with_name(artifact.name + ".sha256")
    manifest_path = artifact.with_name(artifact.name + ".manifest.json")
    if not checksum_path.is_file() or not manifest_path.is_file():
        raise RomBootError("artifact checksum or manifest is missing")
    fields = checksum_path.read_text(encoding="utf-8").strip().split()
    if len(fields) != 2 or fields[1] != artifact.name:
        raise RomBootError("invalid artifact checksum file")
    digest = sha256_file(artifact)
    if digest != fields[0]:
        raise RomBootError("artifact checksum does not match")
    manifest = load_manifest(manifest_path)
    if manifest.get("image", {}).get("sha256") != digest:
        raise RomBootError("artifact manifest hash does not match")
    if artifact.suffix == ".img":
        verify_raw_image(artifact)
    elif artifact.suffix == ".zst":
        if shutil.which("zstd") is None:
            raise RomBootError("zstd is required to test compressed artifacts")
        _run(["zstd", "--test", "--no-progress", str(artifact)], dict(os.environ))
    else:
        raise RomBootError("unsupported artifact extension")


def _verify_filesystem_magic(stream, partitions: List[Partition]) -> None:
    boot, root, data = partitions
    stream.seek(boot.start_sector * 512 + 54)
    fat16 = stream.read(8)
    stream.seek(boot.start_sector * 512 + 82)
    fat32 = stream.read(8)
    if not (fat16.startswith(b"FAT") or fat32.startswith(b"FAT")):
        raise RomBootError("boot partition does not look like FAT")
    stream.seek(root.start_sector * 512)
    if stream.read(4) != b"hsqs":
        raise RomBootError("root partition is not SquashFS")
    stream.seek(data.start_sector * 512 + 1024 + 56)
    if stream.read(2) != b"\x53\xef":
        raise RomBootError("data partition is not ext2/3/4")


def _validate_buildroot_version(source: Path) -> None:
    try:
        makefile = (source / "Makefile").read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise RomBootError("cannot read Buildroot Makefile") from exc
    marker = "export BR2_VERSION := {}".format(SUPPORTED_BUILDROOT_VERSION)
    if marker not in makefile:
        raise RomBootError(
            "unsupported Buildroot source; expected version {}".format(
                SUPPORTED_BUILDROOT_VERSION
            )
        )


def _configure_custom_splash(build_output: Path, prepared: PreparedBuild) -> None:
    splash = prepared.directory / "rootfs" / "usr" / "share" / "romboot" / "splash.png"
    if not splash.is_file():
        return
    value = str(splash.resolve())
    if '"' in value or "\n" in value:
        raise RomBootError("custom splash path contains unsupported characters")
    config = build_output / ".config"
    try:
        lines = config.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise RomBootError("cannot update Buildroot configuration") from exc
    key = "BR2_PACKAGE_PSPLASH_IMAGE="
    for index, line in enumerate(lines):
        if line.startswith(key):
            lines[index] = '{}"{}"'.format(key, value)
            config.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return
    raise RomBootError("Buildroot configuration does not enable a custom splash")


def _run(command: List[str], environment: Dict[str, str]) -> None:
    try:
        subprocess.run(command, env=environment, check=True)
    except FileNotFoundError as exc:
        raise RomBootError("required command not found: {}".format(command[0])) from exc
    except subprocess.CalledProcessError as exc:
        raise RomBootError(
            "command failed with status {}: {}".format(exc.returncode, command[0])
        ) from exc
