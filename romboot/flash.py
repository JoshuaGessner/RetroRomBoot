"""Conservative removable-device inspection and image flashing."""

import os
import plistlib
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, List, Optional, Tuple

from .errors import RomBootError
from .image import verify_artifact
from .manifest import load_manifest
from .security import require_regular_file

VERIFY_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True)
class Device:
    path: Path
    model: str
    size: int
    removable: bool
    platform: str

    def summary(self) -> str:
        return "Target: {} | {} | {:.1f} GiB | removable={}".format(
            self.path, self.model, self.size / (1024 ** 3), self.removable
        )


def inspect_device(path: Path, image: Path) -> Device:
    verify_artifact(image)
    required = _required_image_bytes(image)
    if not path.is_absolute() or path.parent != Path("/dev"):
        raise RomBootError("flash target must be an explicit whole device under /dev")
    try:
        resolved = path.resolve(strict=True)
        mode = resolved.stat().st_mode
    except OSError as exc:
        raise RomBootError("cannot inspect flash target: {}".format(exc)) from exc
    if resolved.parent != Path("/dev"):
        raise RomBootError("resolved flash target is outside /dev")

    if sys.platform == "darwin":
        device = _inspect_macos(resolved)
    elif sys.platform.startswith("linux"):
        if not stat.S_ISBLK(mode):
            raise RomBootError("flash target is not a block device")
        device = _inspect_linux(resolved)
    else:
        raise RomBootError("flashing is supported only on Linux and macOS")
    if not device.removable:
        raise RomBootError("refusing to flash a device not reported as removable/external")
    if device.size < required:
        raise RomBootError(
            "target is too small: need {} bytes, found {}".format(required, device.size)
        )
    return device


def flash_image(image: Path, device: Device) -> None:
    verify_artifact(image)
    _unmount_device(device)
    stream = None
    process: Optional[subprocess.Popen] = None
    try:
        if image.suffix == ".zst":
            if shutil.which("zstd") is None:
                raise RomBootError("zstd is required to flash compressed images")
            process = subprocess.Popen(["zstd", "-dc", str(image)], stdout=subprocess.PIPE)
            if process.stdout is None:
                raise RomBootError("cannot open zstd output")
            stream = process.stdout
        else:
            stream = image.open("rb")
        first = _write_stream(stream, device.path)
        if process is not None and process.wait() != 0:
            raise RomBootError("zstd failed while decompressing the image")
        with device.path.open("rb", buffering=0) as target:
            observed = target.read(len(first))
        if observed != first:
            raise RomBootError("post-write verification of the first block failed")
        if hasattr(os, "sync"):
            os.sync()
    except PermissionError as exc:
        raise RomBootError("permission denied; rerun the flash command with appropriate privileges") from exc
    finally:
        if stream is not None:
            stream.close()
        if process is not None and process.poll() is None:
            process.terminate()


def _write_stream(source: BinaryIO, target_path: Path) -> bytes:
    first = bytearray()
    with target_path.open("r+b", buffering=0) as target:
        while True:
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            if len(first) < VERIFY_BYTES:
                first.extend(chunk[: VERIFY_BYTES - len(first)])
            target.write(chunk)
        target.flush()
        os.fsync(target.fileno())
    if not first:
        raise RomBootError("image decompressed to no data")
    return bytes(first)


def _inspect_macos(path: Path) -> Device:
    try:
        result = subprocess.run(
            ["diskutil", "info", "-plist", str(path)],
            check=True,
            stdout=subprocess.PIPE,
        )
        info = plistlib.loads(result.stdout)
    except (FileNotFoundError, subprocess.CalledProcessError, plistlib.InvalidFileException) as exc:
        raise RomBootError("diskutil could not inspect {}".format(path)) from exc
    if not info.get("Whole"):
        raise RomBootError("flash target must be a whole disk, not a partition")
    if info.get("Internal", True):
        raise RomBootError("refusing to flash an internal disk")
    return Device(
        path=Path(info.get("DeviceNode", str(path))),
        model=str(info.get("MediaName", "unknown device")),
        size=int(info.get("TotalSize", 0)),
        removable=not bool(info.get("Internal", True)),
        platform="darwin",
    )


def _inspect_linux(path: Path) -> Device:
    name = path.name
    sys_block = Path("/sys/class/block") / name
    if not sys_block.exists() or (sys_block / "partition").exists():
        raise RomBootError("flash target must be a whole block device")
    removable = _read_text(sys_block / "removable") == "1"
    sectors = int(_read_text(sys_block / "size") or "0")
    model = _read_text(sys_block / "device" / "model") or "unknown device"
    root_parent = _linux_root_parent()
    if root_parent == name:
        raise RomBootError("refusing to flash the disk containing the active root filesystem")
    return Device(path, model.strip(), sectors * 512, removable, "linux")


def _linux_root_parent() -> Optional[str]:
    try:
        lines = Path("/proc/self/mounts").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    source = next((line.split()[0] for line in lines if len(line.split()) > 1 and line.split()[1] == "/"), None)
    if not source or not source.startswith("/dev/"):
        return None
    name = Path(source).resolve().name
    node = Path("/sys/class/block") / name
    try:
        return node.resolve().parent.name if (node / "partition").exists() else name
    except OSError:
        return name


def _unmount_device(device: Device) -> None:
    try:
        if device.platform == "darwin":
            subprocess.run(["diskutil", "unmountDisk", str(device.path)], check=True)
            return
        for source, mountpoint in _linux_mounts_for(device.path.name):
            subprocess.run(["umount", mountpoint], check=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise RomBootError("could not unmount all target volumes") from exc


def _linux_mounts_for(parent: str) -> List[Tuple[str, str]]:
    result: List[Tuple[str, str]] = []
    try:
        lines = Path("/proc/self/mounts").read_text(encoding="utf-8").splitlines()
    except OSError:
        return result
    for line in lines:
        fields = line.split()
        if len(fields) < 2 or not fields[0].startswith("/dev/"):
            continue
        name = Path(fields[0]).resolve().name
        node = Path("/sys/class/block") / name
        try:
            owner = node.resolve().parent.name if (node / "partition").exists() else name
        except OSError:
            continue
        if owner == parent:
            result.append((fields[0], fields[1]))
    return result


def _required_image_bytes(image: Path) -> int:
    manifest = load_manifest(image.with_name(image.name + ".manifest.json"))
    partitions = manifest.get("image", {}).get("partitions", [])
    if not partitions:
        raise RomBootError("image manifest has no partition layout")
    return max((int(item["start_sector"]) + int(item["sector_count"])) * 512 for item in partitions)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
