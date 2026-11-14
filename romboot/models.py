"""Validated data models loaded from declarative JSON registries."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .errors import RomBootError


@dataclass(frozen=True)
class BiosSpec:
    id: str
    filenames: Tuple[str, ...]
    required: bool
    sha256: Tuple[str, ...] = ()
    size: Optional[int] = None
    destination: str = "bios"

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "BiosSpec":
        try:
            item = cls(
                id=str(value["id"]),
                filenames=tuple(str(v) for v in value["filenames"]),
                required=bool(value.get("required", True)),
                sha256=tuple(str(v).lower() for v in value.get("sha256", [])),
                size=int(value["size"]) if value.get("size") is not None else None,
                destination=str(value.get("destination", "bios")),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise RomBootError("invalid BIOS registry entry: {}".format(exc)) from exc
        if not item.id or not item.filenames:
            raise RomBootError("BIOS entries require an id and at least one filename")
        return item


@dataclass(frozen=True)
class Platform:
    id: str
    name: str
    aliases: Tuple[str, ...]
    extensions: Tuple[str, ...]
    emulator: str
    core: Optional[str]
    target_support: Tuple[str, ...]
    bios: Tuple[BiosSpec, ...] = ()
    settings: Dict[str, Any] = field(default_factory=dict)
    status: str = "planned"
    notes: str = ""

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "Platform":
        try:
            platform = cls(
                id=str(value["id"]).lower(),
                name=str(value["name"]),
                aliases=tuple(str(v).lower() for v in value.get("aliases", [])),
                extensions=tuple(_normalize_extension(v) for v in value["extensions"]),
                emulator=str(value["emulator"]),
                core=str(value["core"]) if value.get("core") else None,
                target_support=tuple(str(v) for v in value.get("target_support", [])),
                bios=tuple(BiosSpec.from_dict(v) for v in value.get("bios", [])),
                settings=dict(value.get("settings", {})),
                status=str(value.get("status", "planned")),
                notes=str(value.get("notes", "")),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise RomBootError("invalid platform registry entry: {}".format(exc)) from exc
        if not platform.id or not platform.name or not platform.extensions:
            raise RomBootError("platforms require id, name, and extensions")
        if not platform.emulator:
            raise RomBootError("platform {} requires an emulator".format(platform.id))
        return platform

    def matches_name(self, value: str) -> bool:
        normalized = value.lower()
        return normalized == self.id or normalized in self.aliases


def _normalize_extension(value: Any) -> str:
    extension = str(value).lower()
    return extension if extension.startswith(".") else "." + extension
