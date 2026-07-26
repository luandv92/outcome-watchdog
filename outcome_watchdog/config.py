"""Config loading: a YAML or JSON file describing the outcomes to monitor."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .durations import parse_duration

VALID_TYPES = {"file", "log_growth", "command"}


class ConfigError(ValueError):
    pass


@dataclass
class Outcome:
    """One monitored outcome, as parsed from the config file."""

    name: str
    type: str
    freshness: str = "24h"

    # file / log_growth
    path: str | None = None
    change: str = "size"          # "size" | "mtime"  (file only)
    timestamp_field: str | None = None   # log_growth only
    min_new: int = 1              # log_growth only

    # command
    command: str | None = None
    timeout: float = 30.0

    description: str | None = None

    def __post_init__(self) -> None:
        if self.type not in VALID_TYPES:
            raise ConfigError(
                f"outcome {self.name!r}: unknown type {self.type!r}, "
                f"expected one of {sorted(VALID_TYPES)}"
            )
        if self.type in ("file", "log_growth") and not self.path:
            raise ConfigError(f"outcome {self.name!r}: type={self.type!r} requires 'path'")
        if self.type == "command" and not self.command:
            raise ConfigError(f"outcome {self.name!r}: type=command requires 'command'")
        if self.change not in ("size", "mtime"):
            raise ConfigError(f"outcome {self.name!r}: change must be 'size' or 'mtime'")
        # Validate the freshness spec eagerly so bad config fails at load
        # time, not mid-run.
        parse_duration(self.freshness)


@dataclass
class WatchdogConfig:
    outcomes: list[Outcome] = field(default_factory=list)
    state_file: str | None = None


def _read_raw(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError as e:  # pragma: no cover - exercised only w/o pyyaml
            raise ConfigError(
                "reading a .yaml/.yml config requires PyYAML — install it with "
                "'pip install outcome-watchdog[yaml]' or 'pip install pyyaml', "
                "or write your config as .json instead"
            ) from e
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: top-level config must be a mapping/object")
    return data


def load_config(path: str | Path) -> WatchdogConfig:
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"config file not found: {path}")
    raw = _read_raw(path)

    outcomes_raw = raw.get("outcomes")
    if not outcomes_raw or not isinstance(outcomes_raw, list):
        raise ConfigError(f"{path}: 'outcomes' must be a non-empty list")

    outcomes: list[Outcome] = []
    seen_names: set[str] = set()
    for i, o in enumerate(outcomes_raw):
        if not isinstance(o, dict):
            raise ConfigError(f"outcomes[{i}] must be a mapping/object")
        o = dict(o)  # copy, don't mutate caller's structure
        name = o.get("name") or f"outcome-{i}"
        if name in seen_names:
            raise ConfigError(f"duplicate outcome name: {name!r}")
        seen_names.add(name)
        o["name"] = name
        outcomes.append(Outcome(**o))

    state_file = raw.get("state_file")
    return WatchdogConfig(outcomes=outcomes, state_file=state_file)
