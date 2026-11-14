"""Prepare a deterministic, single-game rootfs staging tree."""

import json
import os
import re
import shutil
import struct
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from . import __version__
from .bios import ResolvedBios, resolve_bios
from .errors import RomBootError
from .manifest import file_record, write_manifest
from .models import Platform
from .registry import PlatformRegistry
from .security import RomInput, extract_rom, inspect_rom, require_regular_file, sha256_file

_SAFE_VALUE = re.compile(r"^[A-Za-z0-9._+:/-]+$")


@dataclass(frozen=True)
class PreparedBuild:
    directory: Path
    manifest: Path
    platform: Platform
    rom: RomInput
    target: str


def select_platform(
    registry: PlatformRegistry, rom_path: Path, requested: Optional[str]
) -> Tuple[Platform, RomInput]:
    if requested:
        platform = registry.get(requested)
        return platform, inspect_rom(rom_path, platform.extensions)

    all_extensions = sorted({ext for item in registry.all() for ext in item.extensions})
    rom = inspect_rom(rom_path, all_extensions)
    matches = registry.detect_extension(rom.display_name)
    if not matches:
        raise RomBootError(
            "cannot detect platform from {}; use --platform".format(rom.display_name)
        )
    if len(matches) > 1:
        raise RomBootError(
            "platform detection is ambiguous for {}: {}; use --platform".format(
                rom.display_name, ", ".join(item.id for item in matches)
            )
        )
    return matches[0], rom


def prepare_build(
    registry: PlatformRegistry,
    rom_path: Path,
    target: str,
    workspace: Path,
    requested_platform: Optional[str] = None,
    bios_files: Sequence[Path] = (),
    bios_directory: Optional[Path] = None,
    splash: Optional[Path] = None,
    save_mode: str = "persistent",
) -> PreparedBuild:
    platform, rom = select_platform(registry, rom_path, requested_platform)
    if target not in platform.target_support:
        raise RomBootError(
            "platform {} is not enabled for target {}".format(platform.id, target)
        )
    if save_mode not in ("persistent", "ephemeral", "disabled"):
        raise RomBootError("unsupported save mode: {}".format(save_mode))
    bios = resolve_bios(platform, bios_files, bios_directory)
    splash_source = _validate_splash(splash) if splash is not None else None

    workspace = workspace.resolve()
    if workspace.exists():
        raise RomBootError(
            "build workspace already exists: {}; choose another path".format(workspace)
        )
    rootfs = workspace / "rootfs"
    rootfs.mkdir(parents=True)

    extension = Path(rom.display_name).suffix.lower()
    staged_rom = extract_rom(rom, rootfs / "rom" / ("game" + extension))
    files = [file_record(workspace, staged_rom, "rom")]

    for item in bios:
        destination = rootfs / item.destination / item.filename
        _copy_input(item.source, destination)
        files.append(file_record(workspace, destination, "bios"))

    if splash_source is not None:
        destination = rootfs / "usr" / "share" / "romboot" / "splash.png"
        _copy_input(splash_source, destination)
        files.append(file_record(workspace, destination, "splash"))

    runtime = rootfs / "etc" / "romboot" / "game.env"
    runtime.parent.mkdir(parents=True, exist_ok=True)
    runtime.write_text(
        _runtime_environment(platform, staged_rom, save_mode), encoding="utf-8"
    )
    files.append(file_record(workspace, runtime, "configuration"))

    build_spec = workspace / "build.json"
    spec = {
        "schema_version": 1,
        "target": target,
        "platform": platform.id,
        "emulator": platform.emulator,
        "core": platform.core,
        "staging_root": "rootfs",
        "save_mode": save_mode,
    }
    build_spec.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    files.append(file_record(workspace, build_spec, "build-spec"))

    epoch = _source_date_epoch()
    manifest_value = {
        "romboot_version": __version__,
        "romboot_source_commit": os.environ.get("ROMBOOT_SOURCE_COMMIT", "unversioned"),
        "dependencies": _dependency_lock(),
        "source_date_epoch": epoch,
        "built_at": datetime.fromtimestamp(epoch, timezone.utc).isoformat(),
        "target": target,
        "platform": platform.id,
        "emulator": {"id": platform.emulator, "core": platform.core},
        "rom": {
            "stored_name": staged_rom.name,
            "size": rom.size,
            "sha256": rom.sha256,
            "archive_member": rom.member,
        },
        "bios": [
            {
                "id": item.spec_id,
                "stored_name": item.filename,
                "size": item.size,
                "sha256": item.sha256,
            }
            for item in bios
        ],
        "effective_configuration": {"save_mode": save_mode},
        "files": files,
        "reproducible_expected": False,
        "verification": {
            "structural": False,
            "qemu": False,
            "physical_hardware": False,
        },
    }
    manifest_path = workspace / "manifest.json"
    write_manifest(manifest_path, manifest_value)
    return PreparedBuild(workspace, manifest_path, platform, rom, target)


def _runtime_environment(
    platform: Platform, rom_path: Path, save_mode: str
) -> str:
    settings = platform.settings
    required = ("emulator_path", "core_path", "retroarch_config")
    missing = [key for key in required if not settings.get(key)]
    if missing:
        raise RomBootError(
            "platform {} lacks runtime settings: {}".format(
                platform.id, ", ".join(missing)
            )
        )
    values = {
        "ROMBOOT_PLATFORM": platform.id,
        "ROMBOOT_EMULATOR": str(settings["emulator_path"]),
        "ROMBOOT_CORE": str(settings["core_path"]),
        "ROMBOOT_ROM": "/rom/" + rom_path.name,
        "ROMBOOT_RETROARCH_CONFIG": str(settings["retroarch_config"]),
        "ROMBOOT_EXIT_POLICY": "shutdown",
        "ROMBOOT_LOG_BYTES": "65536",
        "ROMBOOT_SAVE_MODE": save_mode,
    }
    lines = []
    for key, value in values.items():
        if not _SAFE_VALUE.fullmatch(value) or "\n" in value:
            raise RomBootError("unsafe generated runtime value for {}".format(key))
        lines.append("{}='{}'".format(key, value))
    return "\n".join(lines) + "\n"


def _validate_splash(path: Path) -> Path:
    source = require_regular_file(path, "splash")
    if source.suffix.lower() != ".png":
        raise RomBootError("custom splash must be a PNG file")
    if source.stat().st_size > 20 * 1024 * 1024:
        raise RomBootError("custom splash exceeds the 20 MiB limit")
    with source.open("rb") as stream:
        header = stream.read(24)
    valid_header = (
        len(header) == 24
        and header[:8] == b"\x89PNG\r\n\x1a\n"
        and header[8:12] == b"\x00\x00\x00\r"
        and header[12:16] == b"IHDR"
    )
    if not valid_header:
        raise RomBootError("custom splash does not have a valid PNG header")
    width, height = struct.unpack(">II", header[16:24])
    if width < 1 or height < 1 or width > 4096 or height > 4096 or width * height > 8_000_000:
        raise RomBootError("custom splash dimensions exceed the 4096 px / 8 MP limit")
    return source

def _copy_input(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as input_stream, destination.open("xb") as output_stream:
        shutil.copyfileobj(input_stream, output_stream, length=1024 * 1024)


def _dependency_lock():
    source_tree = Path(__file__).resolve().parent.parent / "dependencies.lock.json"
    packaged = Path(__file__).resolve().parent / "data" / "dependencies.lock.json"
    path = source_tree if source_tree.is_file() else packaged
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RomBootError("cannot read dependency lock: {}".format(exc)) from exc
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise RomBootError("unsupported dependency lock schema")
    return value.get("dependencies", {})


def _source_date_epoch() -> int:
    raw = os.environ.get("SOURCE_DATE_EPOCH", "0")
    try:
        epoch = int(raw)
    except ValueError as exc:
        raise RomBootError("SOURCE_DATE_EPOCH must be an integer") from exc
    if epoch < 0:
        raise RomBootError("SOURCE_DATE_EPOCH cannot be negative")
    return epoch
