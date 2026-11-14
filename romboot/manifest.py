"""Canonical build manifests and staged-output verification."""

import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .errors import RomBootError
from .security import sha256_file

MANIFEST_SCHEMA_VERSION = 1


def write_manifest(path: Path, value: Dict[str, Any]) -> None:
    payload = dict(value)
    payload["schema_version"] = MANIFEST_SCHEMA_VERSION
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, indent=2, sort_keys=True, separators=(",", ": ")) + "\n"
    path.write_text(encoded, encoding="utf-8")


def load_manifest(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RomBootError("cannot read manifest {}: {}".format(path, exc)) from exc
    if not isinstance(value, dict) or value.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise RomBootError("unsupported or invalid manifest: {}".format(path))
    return value


def verify_staging(directory: Path) -> List[str]:
    manifest_path = directory / "manifest.json"
    manifest = load_manifest(manifest_path)
    failures: List[str] = []
    for item in manifest.get("files", []):
        relative = item.get("path", "")
        expected = item.get("sha256", "")
        candidate = _safe_child(directory, relative)
        if not candidate.is_file():
            failures.append("missing {}".format(relative))
        elif sha256_file(candidate) != expected:
            failures.append("hash mismatch {}".format(relative))
    roms = [item for item in manifest.get("files", []) if item.get("kind") == "rom"]
    if len(roms) != 1:
        failures.append("manifest must identify exactly one ROM")
    return failures


def file_record(root: Path, path: Path, kind: str) -> Dict[str, Any]:
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    try:
        relative = resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise RomBootError("manifest file escapes staging root: {}".format(path)) from exc
    return {
        "kind": kind,
        "path": relative.as_posix(),
        "size": resolved_path.stat().st_size,
        "sha256": sha256_file(resolved_path),
    }


def _safe_child(root: Path, relative: str) -> Path:
    if not relative:
        raise RomBootError("manifest contains an empty path")
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise RomBootError("manifest path escapes staging root: {}".format(relative)) from exc
    return candidate
