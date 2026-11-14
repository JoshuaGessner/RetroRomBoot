"""Subprocess entry point that performs one image build.

Run as ``python -m romboot_web.build_worker <spec.json>``.  It calls the same
``romboot`` staging and build functions the CLI uses, pointing them at a warm,
per-target Buildroot output directory and a shared download cache so repeat
builds skip the toolchain rebuild.  All output goes to stdout/stderr, which the
job manager captures line by line for the live log.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from romboot.builder import prepare_build
from romboot.errors import RomBootError
from romboot.image import run_buildroot
from romboot.registry import PlatformRegistry, default_registry_path


def _opt_path(value) -> "Path | None":
    return Path(value) if value else None


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        print("usage: python -m romboot_web.build_worker <spec.json>", file=sys.stderr)
        return 2
    spec = json.loads(Path(argv[0]).read_text(encoding="utf-8"))

    buildroot_dir = _opt_path(spec.get("buildroot_dir"))
    if buildroot_dir is None or not (buildroot_dir / "Makefile").is_file():
        print("romboot-web: no Buildroot source configured; cannot compile an image.",
              file=sys.stderr)
        print("Set BUILDROOT_DIR to the pinned Buildroot 2025.02.16 checkout.", file=sys.stderr)
        return 2

    try:
        registry = PlatformRegistry.load(default_registry_path())
        prepared = prepare_build(
            registry=registry,
            rom_path=Path(spec["rom"]),
            target=str(spec["target"]),
            workspace=Path(spec["workspace"]),
            requested_platform=spec.get("platform"),
            bios_files=[Path(p) for p in spec.get("bios", [])],
            splash=_opt_path(spec.get("splash")),
            save_mode=str(spec.get("save_mode", "persistent")),
        )
        print("Prepared {} staging at {}".format(prepared.platform.id, prepared.directory),
              flush=True)
        built = run_buildroot(
            prepared,
            buildroot_dir,
            Path(spec["external_tree"]),
            Path(spec["output"]),
            jobs=int(spec.get("jobs", 1)),
            build_output=_opt_path(spec.get("build_output")),
            dl_dir=_opt_path(spec.get("dl_dir")),
        )
    except RomBootError as exc:
        print("romboot-web: error: {}".format(exc), file=sys.stderr)
        return 2
    print("Image: {}".format(built.path), flush=True)
    print("SHA-256: {}".format(built.sha256), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
