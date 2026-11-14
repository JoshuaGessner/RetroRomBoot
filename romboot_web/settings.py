"""Runtime configuration for the RomBoot web service, resolved from the
environment with defaults suited to the Docker container layout.

Directory layout (all overridable):

    /data                       ROMBOOT_WEB_DATA        mutable per-run state
      uploads/<id>/<name>         user-supplied ROM/BIOS/splash files
      jobs/<id>/                  per-build workspace, log, and artifact
    /cache                      ROMBOOT_WEB_CACHE       reused across builds
      build/<target>/             warm Buildroot output (toolchain + packages)
      dl/                         shared Buildroot download cache
    /opt/romboot                ROMBOOT_PROJECT_ROOT    repo checkout (external tree)
    /opt/buildroot              BUILDROOT_DIR           pinned Buildroot source
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def _env_path(name: str, default: str) -> Path:
    return Path(os.environ.get(name, default)).expanduser()


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _default_project_root() -> Path:
    # The Buildroot external tree lives at <repo>/buildroot; the repo root is the
    # parent of the installed ``romboot`` package when installed editable.
    import romboot

    return Path(romboot.__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    cache_dir: Path
    project_root: Path
    buildroot_dir: Optional[Path]
    host: str
    port: int
    jobs: int
    token: Optional[str]
    max_upload_bytes: int
    output_suffix: str  # ".img.zst" (default) or ".img"

    @classmethod
    def from_env(cls) -> "Settings":
        project_root = _env_path("ROMBOOT_PROJECT_ROOT", str(_default_project_root()))
        buildroot_raw = os.environ.get("BUILDROOT_DIR", "/opt/buildroot")
        buildroot_dir = Path(buildroot_raw).expanduser() if buildroot_raw else None
        suffix = os.environ.get("ROMBOOT_WEB_OUTPUT_SUFFIX", ".img.zst")
        if suffix not in (".img", ".img.zst"):
            suffix = ".img.zst"
        return cls(
            data_dir=_env_path("ROMBOOT_WEB_DATA", "/data"),
            cache_dir=_env_path("ROMBOOT_WEB_CACHE", "/cache"),
            project_root=project_root,
            buildroot_dir=buildroot_dir,
            host=os.environ.get("ROMBOOT_WEB_HOST", "127.0.0.1"),
            port=_env_int("ROMBOOT_WEB_PORT", 8080),
            jobs=_env_int("ROMBOOT_WEB_JOBS", os.cpu_count() or 1),
            token=os.environ.get("ROMBOOT_WEB_TOKEN") or None,
            max_upload_bytes=_env_int("ROMBOOT_WEB_MAX_UPLOAD", 4 * 1024 * 1024 * 1024),
            output_suffix=suffix,
        )

    # --- derived paths -----------------------------------------------------
    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def jobs_dir(self) -> Path:
        return self.data_dir / "jobs"

    @property
    def external_tree(self) -> Path:
        return self.project_root / "buildroot"

    @property
    def dl_dir(self) -> Path:
        return self.cache_dir / "dl"

    def warm_output_dir(self, target: str) -> Path:
        """Per-target Buildroot output reused across builds so the toolchain is
        compiled once.  The target name is validated by the registry before this
        is called, so it is a safe path component."""
        return self.cache_dir / "build" / target

    def ensure_dirs(self) -> None:
        for path in (self.uploads_dir, self.jobs_dir, self.dl_dir, self.cache_dir / "build"):
            path.mkdir(parents=True, exist_ok=True)

    def buildroot_available(self) -> bool:
        return self.buildroot_dir is not None and (self.buildroot_dir / "Makefile").is_file()
