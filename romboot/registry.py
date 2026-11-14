"""Loading and validation for platform registry files."""

import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

from .errors import RomBootError
from .models import Platform


class PlatformRegistry:
    def __init__(self, platforms: Iterable[Platform]):
        items = list(platforms)
        self._platforms = {platform.id: platform for platform in items}
        if len(self._platforms) != len(items):
            raise RomBootError("duplicate platform id in registry")
        if not self._platforms:
            raise RomBootError("the platform registry is empty")
        self._validate()

    @classmethod
    def load(cls, directory: Path) -> "PlatformRegistry":
        if not directory.is_dir():
            raise RomBootError("platform registry not found: {}".format(directory))
        platforms: List[Platform] = []
        for path in sorted(directory.glob("*.json")):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise RomBootError("cannot read platform {}: {}".format(path, exc)) from exc
            if not isinstance(value, dict) or value.get("schema_version") != 1:
                raise RomBootError("{} must use platform schema_version 1".format(path))
            platforms.append(Platform.from_dict(value))
        return cls(platforms)

    def all(self) -> List[Platform]:
        return sorted(self._platforms.values(), key=lambda item: item.id)

    def get(self, value: str) -> Platform:
        matches = [platform for platform in self._platforms.values() if platform.matches_name(value)]
        if not matches:
            raise RomBootError(
                "unknown platform {!r}; available: {}".format(
                    value, ", ".join(sorted(self._platforms))
                )
            )
        if len(matches) > 1:
            raise RomBootError("ambiguous platform alias {!r}".format(value))
        return matches[0]

    def detect_extension(self, filename: str) -> List[Platform]:
        extension = Path(filename).suffix.lower()
        return [platform for platform in self.all() if extension in platform.extensions]

    def _validate(self) -> None:
        seen_ids: Set[str] = set()
        seen_names: Dict[str, str] = {}
        for platform in self._platforms.values():
            if platform.id in seen_ids:
                raise RomBootError("duplicate platform id: {}".format(platform.id))
            seen_ids.add(platform.id)
            for value in (platform.id,) + platform.aliases:
                owner = seen_names.get(value)
                if owner and owner != platform.id:
                    raise RomBootError(
                        "platform alias {!r} is shared by {} and {}".format(
                            value, owner, platform.id
                        )
                    )
                seen_names[value] = platform.id
            for bios in platform.bios:
                if Path(bios.destination).is_absolute() or ".." in Path(bios.destination).parts:
                    raise RomBootError(
                        "platform {} has unsafe BIOS destination {}".format(
                            platform.id, bios.destination
                        )
                    )


def default_registry_path() -> Path:
    source_tree = Path(__file__).resolve().parent.parent / "platforms"
    if source_tree.is_dir():
        return source_tree
    return Path(__file__).resolve().parent / "data" / "platforms"
