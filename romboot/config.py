"""Versioned host configuration with explicit precedence."""

import json
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from .errors import RomBootError

ALLOWED_KEYS = {"target", "platform", "save_mode", "buildroot_dir", "jobs"}
BUILTIN_DEFAULTS: Dict[str, Any] = {
    "target": "rpi4",
    "save_mode": "persistent",
    "jobs": 1,
}


def load_effective_config(
    project_config: Optional[Path] = None,
    user_config: Optional[Path] = None,
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    result = dict(BUILTIN_DEFAULTS)
    default_user = Path.home() / ".config" / "romboot" / "config.json"
    for path in (user_config or default_user, project_config or Path("romboot.json")):
        if path.is_file():
            result.update(_load_file(path))
    for key, value in (overrides or {}).items():
        if value is not None:
            if key not in ALLOWED_KEYS:
                raise RomBootError("unknown configuration override: {}".format(key))
            result[key] = value
    if result.get("save_mode") not in ("persistent", "ephemeral", "disabled"):
        raise RomBootError("invalid configured save_mode")
    try:
        result["jobs"] = int(result["jobs"])
    except (TypeError, ValueError) as exc:
        raise RomBootError("configured jobs must be an integer") from exc
    if result["jobs"] < 1:
        raise RomBootError("configured jobs must be at least 1")
    return result


def _load_file(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RomBootError("cannot read configuration {}: {}".format(path, exc)) from exc
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise RomBootError("{} must use configuration schema_version 1".format(path))
    unknown = set(value) - ALLOWED_KEYS - {"schema_version"}
    if unknown:
        raise RomBootError(
            "unknown configuration fields in {}: {}".format(path, ", ".join(sorted(unknown)))
        )
    return {key: value[key] for key in ALLOWED_KEYS if key in value}
