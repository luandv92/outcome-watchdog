"""Graduated verdicts for outcome checks.

The core design principle of this whole package: never collapse a check down
to a binary ok/broken. A monitored job can be in one of four states:

  OK          - fresh, and something actually changed since the last check.
  STALE       - past its expected freshness window (nothing new for too long).
  NO_CHANGE   - checked within the freshness window, but the tracked value
                (file size, line count, command output, ...) did not move.
                This is exactly the "exited 0 but did nothing" failure mode.
  UNVERIFIED  - the check itself could not be performed (file missing,
                command not found, permission denied, ...). This is
                deliberately NOT treated as a failure: a tool that can't see
                the outcome has no evidence of a problem, only an inability
                to look. Reporting UNVERIFIED as "broken" is how false
                positives happen and trust in the watchdog erodes.

Only OK and NO_CHANGE/STALE are actionable. UNVERIFIED is always informative,
never an alarm — the CLI still exits non-zero for STALE/NO_CHANGE so it can
gate CI or wake someone up, but never for UNVERIFIED.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Verdict(str, Enum):
    OK = "OK"
    STALE = "STALE"
    NO_CHANGE = "NO_CHANGE"
    UNVERIFIED = "UNVERIFIED"

    @property
    def is_failure(self) -> bool:
        """Only these two verdicts represent confirmed problems worth
        failing a CI run or paging someone over. STALE/NO_CHANGE both mean
        "we successfully checked, and something is actually wrong"."""
        return self in (Verdict.STALE, Verdict.NO_CHANGE)

    @property
    def emoji(self) -> str:
        return {
            Verdict.OK: "\U0001F7E2",           # green circle
            Verdict.STALE: "\U0001F7E1",        # yellow circle
            Verdict.NO_CHANGE: "\U0001F534",    # red circle
            Verdict.UNVERIFIED: "⚪",       # white circle
        }[self]


@dataclass
class OutcomeResult:
    """The result of checking one monitored outcome."""

    name: str
    verdict: Verdict
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "verdict": self.verdict.value,
            "message": self.message,
            "details": self.details,
        }
