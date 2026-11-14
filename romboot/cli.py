"""Command-line interface for RomBoot."""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Optional, Sequence

from . import __version__
from .builder import prepare_build, select_platform
from .config import load_effective_config
from .errors import RomBootError
from .image import run_buildroot, verify_artifact, verify_raw_image
from .manifest import verify_staging
from .registry import PlatformRegistry, default_registry_path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="romboot",
        description="Build a minimal Raspberry Pi image containing one user-supplied game.",
    )
    parser.add_argument("--version", action="version", version="%(prog)s " + __version__)
    parser.add_argument(
        "--registry", type=Path, default=default_registry_path(), help=argparse.SUPPRESS
    )
    commands = parser.add_subparsers(dest="command")

    ui = commands.add_parser(
        "ui", help="interactive guided menu (also the default when no command is given)"
    )
    ui.add_argument("--buildroot-dir", type=Path)
    ui.add_argument("--output", type=Path)
    ui.add_argument("--jobs", type=int)

    doctor = commands.add_parser("doctor", help="check host-side prerequisites")
    doctor.add_argument("--buildroot-dir", type=Path)

    commands.add_parser("platforms", help="list registered console platforms")

    inspect = commands.add_parser("inspect", help="inspect a ROM without executing it")
    inspect.add_argument("rom", type=Path)
    inspect.add_argument("--platform")

    build = commands.add_parser("build", help="prepare or build a one-game image")
    build.add_argument("--rom", type=Path, required=True)
    build.add_argument("--platform")
    build.add_argument("--target")
    build.add_argument("--config", type=Path)
    build.add_argument("--bios", type=Path, action="append", default=[])
    build.add_argument("--bios-dir", type=Path)
    build.add_argument("--splash", type=Path)
    build.add_argument(
        "--save-mode", choices=("persistent", "ephemeral", "disabled")
    )
    build.add_argument("--workspace", type=Path)
    build.add_argument("--prepare-only", action="store_true")
    build.add_argument("--buildroot-dir", type=Path)
    build.add_argument("--output", type=Path)
    build.add_argument("--jobs", type=int)

    verify = commands.add_parser("verify", help="verify a staging tree or image artifact")
    verify.add_argument("path", type=Path)
    verify.add_argument("--raw", action="store_true", help="verify an unpackaged raw SD-card image")

    flash = commands.add_parser("flash", help="safely write an image to removable media")
    flash.add_argument("image", type=Path)
    flash.add_argument("device", type=Path)
    flash.add_argument("--yes", action="store_true", help="skip the typed confirmation")
    flash.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        registry = PlatformRegistry.load(args.registry)
        command = getattr(args, "command", None)
        if command is None or command == "ui":
            from .wizard import run_wizard

            buildroot = getattr(args, "buildroot_dir", None) or _buildroot_from_environment()
            return run_wizard(
                registry,
                buildroot=buildroot,
                output_dir=getattr(args, "output", None),
                jobs=getattr(args, "jobs", None),
                project_root=PROJECT_ROOT,
            )
        if command == "doctor":
            return _doctor(args, registry)
        if command == "platforms":
            return _platforms(registry)
        if command == "inspect":
            return _inspect(args, registry)
        if command == "build":
            return _build(args, registry)
        if command == "verify":
            return _verify(args)
        if command == "flash":
            return _flash(args)
        parser.error("unknown command")
    except RomBootError as exc:
        print("romboot: error: {}".format(exc), file=sys.stderr)
        return 2
    return 0


def _doctor(args, registry: PlatformRegistry) -> int:
    checks = []
    checks.append(("Python", sys.version_info >= (3, 9), sys.version.split()[0]))
    checks.append(("platform registry", bool(registry.all()), "{} platforms".format(len(registry.all()))))
    for command, required in (("make", True), ("zstd", False)):
        location = shutil.which(command)
        checks.append((command, bool(location) or not required, location or "not found"))
    buildroot = args.buildroot_dir or _buildroot_from_environment()
    checks.append(
        (
            "Buildroot source",
            buildroot is not None and (buildroot / "Makefile").is_file(),
            str(buildroot) if buildroot else "set BUILDROOT_DIR or pass --buildroot-dir",
        )
    )
    for name, okay, detail in checks:
        print("{:<20} {:<5} {}".format(name, "ok" if okay else "MISS", detail))
    print("Note: a successful doctor check does not prove physical Raspberry Pi compatibility.")
    return 0 if all(okay for _, okay, _ in checks[:3]) else 1


def _platforms(registry: PlatformRegistry) -> int:
    print("{:<10} {:<24} {:<20} {}".format("ID", "STATUS", "TARGETS", "NAME"))
    for platform in registry.all():
        print(
            "{:<10} {:<24} {:<20} {}".format(
                platform.id,
                platform.status,
                ",".join(platform.target_support) or "-",
                platform.name,
            )
        )
    return 0


def _inspect(args, registry: PlatformRegistry) -> int:
    platform, rom = select_platform(registry, args.rom, args.platform)
    value = {
        "platform": platform.id,
        "platform_status": platform.status,
        "rom_name": rom.display_name,
        "archive_member": rom.member,
        "size": rom.size,
        "sha256": rom.sha256,
        "required_bios": [item.id for item in platform.bios if item.required],
    }
    print(json.dumps(value, indent=2, sort_keys=True))
    return 0


def _build(args, registry: PlatformRegistry) -> int:
    cfg = load_effective_config(
        project_config=args.config,
        overrides={
            "target": args.target,
            "platform": args.platform,
            "save_mode": args.save_mode,
            "buildroot_dir": str(args.buildroot_dir) if args.buildroot_dir else None,
            "jobs": args.jobs,
        },
    )
    target = str(cfg["target"])
    platform = str(cfg["platform"]) if cfg.get("platform") else None
    save_mode = str(cfg["save_mode"])
    workspace = args.workspace
    if workspace is None:
        safe_stem = "".join(c if c.isalnum() or c in "-_" else "-" for c in args.rom.stem)
        workspace = Path("build") / (safe_stem[:48] + "-" + target)
    prepared = prepare_build(
        registry=registry,
        rom_path=args.rom,
        target=target,
        workspace=workspace,
        requested_platform=platform,
        bios_files=args.bios,
        bios_directory=args.bios_dir,
        splash=args.splash,
        save_mode=save_mode,
    )
    print("Prepared {} at {}".format(prepared.platform.id, prepared.directory))
    if args.prepare_only:
        print("Staging verification: ok")
        return 0
    configured_buildroot = Path(str(cfg["buildroot_dir"])).expanduser() if cfg.get("buildroot_dir") else None
    buildroot = configured_buildroot or _buildroot_from_environment()
    if buildroot is None:
        raise RomBootError(
            "a Buildroot source checkout is required; pass --buildroot-dir or set BUILDROOT_DIR"
        )
    if args.output is None:
        raise RomBootError("--output is required unless --prepare-only is used")
    built = run_buildroot(
        prepared,
        buildroot,
        PROJECT_ROOT / "buildroot",
        args.output,
        jobs=int(cfg["jobs"]),
    )
    print("Image: {}".format(built.path))
    print("SHA-256: {}".format(built.sha256))
    print("Manifest: {}".format(built.manifest))
    return 0


def _verify(args) -> int:
    if args.raw:
        if args.path.is_dir():
            raise RomBootError("--raw requires an image file")
        partitions = verify_raw_image(args.path)
        print("Raw image verification: ok ({} partitions)".format(len(partitions)))
    elif args.path.is_dir():
        failures = verify_staging(args.path)
        if failures:
            raise RomBootError("staging verification failed: {}".format("; ".join(failures)))
        print("Staging verification: ok")
    else:
        verify_artifact(args.path)
        print("Artifact verification: ok")
    return 0


def _flash(args) -> int:
    from .flash import flash_image, inspect_device

    device = inspect_device(args.device, args.image)
    print(device.summary())
    if args.dry_run:
        print("Dry run: no data written")
        return 0
    if not args.yes:
        expected = "ERASE {}".format(device.path)
        response = input("Type {!r} to continue: ".format(expected))
        if response != expected:
            raise RomBootError("confirmation did not match; nothing was written")
    flash_image(args.image, device)
    print("Image written and first-block verification passed")
    return 0


def _buildroot_from_environment() -> Optional[Path]:
    raw = os.environ.get("BUILDROOT_DIR")
    return Path(raw).expanduser() if raw else None
