"""Persisted state between runs.

Change-detection needs a memory of "what did we see last time" — a single
run can't tell whether a file's size grew unless it remembers the previous
size. This is a tiny JSON key/value store, one entry per outcome name, saved
next to (or wherever the user points) the config file.

Deliberately simple (no locking, no schema migrations) — it stores small
scalars per outcome, not a database. If it's ever corrupt or unreadable, the
engine treats that outcome as having no prior state rather than crashing —
consistent with "a tool failure to check must never be reported as
confirmed-broken".
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class StateStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._data: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            self._data = {}
            return
        try:
            self._data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(self._data, dict):
                self._data = {}
        except Exception:
            # Corrupt state file -> start fresh rather than crash. Losing
            # change-history for one run degrades detection (everything looks
            # "new" once) but never produces a false confirmed-broken verdict.
            self._data = {}

    def get(self, name: str) -> dict[str, Any] | None:
        return self._data.get(name)

    def set(self, name: str, value: dict[str, Any]) -> None:
        self._data[name] = value

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(self._data, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.path)
