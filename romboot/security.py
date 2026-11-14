"""Security boundaries for user-controlled files and archives."""

import hashlib
import os
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable, List, Optional, Sequence

from .errors import RomBootError

MAX_ARCHIVE_ENTRIES = 256
MAX_ARCHIVE_BYTES = 1024 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200
HASH_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class RomInput:
    source: Path
    member: Optional[str]
    display_name: str
    size: int
    sha256: str


def require_regular_file(path: Path, label: str) -> Path:
    try:
        info = path.lstat()
    except OSError as exc:
        raise RomBootError("{} cannot be read: {}".format(label, exc)) from exc
    if stat.S_ISLNK(info.st_mode):
        raise RomBootError("{} must not be a symbolic link: {}".format(label, path))
    if not stat.S_ISREG(info.st_mode):
        raise RomBootError("{} must be a regular file: {}".format(label, path))
    return path.resolve()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(HASH_CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def inspect_rom(path: Path, accepted_extensions: Optional[Sequence[str]] = None) -> RomInput:
    source = require_regular_file(path, "ROM")
    if source.suffix.lower() == ".zip":
        return _inspect_zip(source, accepted_extensions)
    if accepted_extensions and source.suffix.lower() not in accepted_extensions:
        raise RomBootError(
            "ROM extension {} is not accepted; expected {}".format(
                source.suffix or "<none>", ", ".join(accepted_extensions)
            )
        )
    return RomInput(source, None, source.name, source.stat().st_size, sha256_file(source))


def extract_rom(rom: RomInput, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise RomBootError("refusing to overwrite staged ROM: {}".format(destination))
    if rom.member is None:
        _copy_exclusive(rom.source, destination)
    else:
        with zipfile.ZipFile(str(rom.source), "r") as archive:
            with archive.open(rom.member, "r") as source, destination.open("xb") as output:
                remaining = MAX_ARCHIVE_BYTES + 1
                while remaining > 0:
                    chunk = source.read(min(HASH_CHUNK_SIZE, remaining))
                    if not chunk:
                        break
                    output.write(chunk)
                    remaining -= len(chunk)
                if remaining <= 0 and source.read(1):
                    destination.unlink(missing_ok=True)
                    raise RomBootError("archive member exceeds extraction limit")
    if sha256_file(destination) != rom.sha256:
        destination.unlink(missing_ok=True)
        raise RomBootError("staged ROM hash does not match inspected input")
    return destination


def _inspect_zip(path: Path, accepted_extensions: Optional[Sequence[str]]) -> RomInput:
    candidates: List[zipfile.ZipInfo] = []
    try:
        with zipfile.ZipFile(str(path), "r") as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ARCHIVE_ENTRIES:
                raise RomBootError("ROM archive contains too many entries")
            total = 0
            for entry in entries:
                _validate_zip_entry(entry)
                if entry.is_dir():
                    continue
                total += entry.file_size
                if total > MAX_ARCHIVE_BYTES:
                    raise RomBootError("ROM archive is too large when expanded")
                if entry.file_size and entry.compress_size == 0:
                    raise RomBootError("ROM archive contains an invalid compressed entry")
                if entry.compress_size and entry.file_size / entry.compress_size > MAX_COMPRESSION_RATIO:
                    raise RomBootError("ROM archive exceeds the compression-ratio limit")
                extension = PurePosixPath(entry.filename).suffix.lower()
                if not accepted_extensions or extension in accepted_extensions:
                    candidates.append(entry)
            if len(candidates) != 1:
                raise RomBootError(
                    "ROM archive must contain exactly one matching game; found {}".format(
                        len(candidates)
                    )
                )
            selected = candidates[0]
            digest = hashlib.sha256()
            with archive.open(selected, "r") as stream:
                while True:
                    chunk = stream.read(HASH_CHUNK_SIZE)
                    if not chunk:
                        break
                    digest.update(chunk)
            return RomInput(path, selected.filename, PurePosixPath(selected.filename).name, selected.file_size, digest.hexdigest())
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        if isinstance(exc, RomBootError):
            raise
        raise RomBootError("cannot inspect ROM archive: {}".format(exc)) from exc


def _validate_zip_entry(entry: zipfile.ZipInfo) -> None:
    name = PurePosixPath(entry.filename)
    if name.is_absolute() or ".." in name.parts or "" in name.parts:
        raise RomBootError("ROM archive contains an unsafe path")
    unix_mode = entry.external_attr >> 16
    if unix_mode and stat.S_ISLNK(unix_mode):
        raise RomBootError("ROM archive must not contain symbolic links")


def _copy_exclusive(source: Path, destination: Path) -> None:
    with source.open("rb") as input_stream, destination.open("xb") as output_stream:
        while True:
            chunk = input_stream.read(HASH_CHUNK_SIZE)
            if not chunk:
                break
            output_stream.write(chunk)
