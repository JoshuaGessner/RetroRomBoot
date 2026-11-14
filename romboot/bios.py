"""Resolve and validate user-supplied BIOS files without fetching content."""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from .errors import RomBootError
from .models import BiosSpec, Platform
from .security import require_regular_file, sha256_file


@dataclass(frozen=True)
class ResolvedBios:
    spec_id: str
    source: Path
    destination: str
    filename: str
    size: int
    sha256: str


def resolve_bios(
    platform: Platform,
    files: Sequence[Path] = (),
    directory: Optional[Path] = None,
) -> List[ResolvedBios]:
    candidates: Dict[str, Path] = {}
    for path in files:
        resolved = require_regular_file(path, "BIOS")
        candidates[resolved.name.lower()] = resolved
    if directory is not None:
        if not directory.is_dir():
            raise RomBootError("BIOS directory not found: {}".format(directory))
        for path in directory.iterdir():
            if path.is_file() and not path.is_symlink():
                candidates.setdefault(path.name.lower(), path.resolve())

    result: List[ResolvedBios] = []
    missing: List[str] = []
    for spec in platform.bios:
        source = _find_candidate(spec, candidates)
        if source is None:
            if spec.required:
                missing.append("{} ({})".format(spec.id, " or ".join(spec.filenames)))
            continue
        size = source.stat().st_size
        if spec.size is not None and size != spec.size:
            raise RomBootError(
                "BIOS {} has size {}, expected {}".format(source.name, size, spec.size)
            )
        digest = sha256_file(source)
        if spec.sha256 and digest not in spec.sha256:
            raise RomBootError(
                "BIOS {} has SHA-256 {}, which is not accepted for {}".format(
                    source.name, digest, spec.id
                )
            )
        result.append(
            ResolvedBios(spec.id, source, spec.destination, source.name, size, digest)
        )
    if missing:
        raise RomBootError("missing required BIOS: {}".format(", ".join(missing)))
    return result


def _find_candidate(spec: BiosSpec, candidates: Dict[str, Path]) -> Optional[Path]:
    for filename in spec.filenames:
        candidate = candidates.get(filename.lower())
        if candidate is not None:
            return candidate
    return None
