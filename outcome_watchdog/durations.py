"""Tiny duration-string parser: "24h", "30m", "2d", "90s", or a bare number
of seconds (int/float/str). Kept dependency-free on purpose."""
from __future__ import annotations

import re
from datetime import timedelta

_UNIT_SECONDS = {
    "s": 1,
    "sec": 1,
    "secs": 1,
    "second": 1,
    "seconds": 1,
    "m": 60,
    "min": 60,
    "mins": 60,
    "minute": 60,
    "minutes": 60,
    "h": 3600,
    "hr": 3600,
    "hrs": 3600,
    "hour": 3600,
    "hours": 3600,
    "d": 86400,
    "day": 86400,
    "days": 86400,
    "w": 604800,
    "week": 604800,
    "weeks": 604800,
}

_PATTERN = re.compile(r"^\s*([0-9]*\.?[0-9]+)\s*([a-zA-Z]+)?\s*$")


def parse_duration(spec) -> timedelta:
    """Parse a duration spec into a timedelta.

    Accepts: "24h", "30m", "2d", "90s", "1.5h", or a bare number (seconds).
    Raises ValueError on anything it can't parse.
    """
    if isinstance(spec, timedelta):
        return spec
    if isinstance(spec, (int, float)):
        return timedelta(seconds=float(spec))
    if not isinstance(spec, str):
        raise ValueError(f"cannot parse duration from {spec!r}")

    m = _PATTERN.match(spec)
    if not m:
        raise ValueError(f"invalid duration string: {spec!r}")
    value, unit = m.group(1), m.group(2)
    seconds_per_unit = 1 if unit is None else _UNIT_SECONDS.get(unit.lower())
    if seconds_per_unit is None:
        raise ValueError(f"unknown duration unit {unit!r} in {spec!r}")
    return timedelta(seconds=float(value) * seconds_per_unit)
