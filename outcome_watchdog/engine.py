"""Runs every configured outcome check and returns the results."""
from __future__ import annotations

from datetime import datetime, timezone

from .checks import check_command, check_file, check_log_growth
from .config import WatchdogConfig
from .state import StateStore
from .verdict import OutcomeResult, Verdict

_DISPATCH = {
    "file": check_file,
    "log_growth": check_log_growth,
    "command": check_command,
}


def run_outcomes(
    config: WatchdogConfig,
    state: StateStore,
    now: datetime | None = None,
) -> list[OutcomeResult]:
    now = now or datetime.now(timezone.utc)
    results: list[OutcomeResult] = []
    for outcome in config.outcomes:
        check_fn = _DISPATCH[outcome.type]
        try:
            result = check_fn(outcome, state, now)
        except Exception as e:
            # A bug in a check (or something wildly unexpected, e.g. a
            # permissions error we didn't anticipate) must never be reported
            # as a confirmed failure — it's an inability to check, full stop.
            result = OutcomeResult(
                outcome.name,
                Verdict.UNVERIFIED,
                f"check raised an unexpected error: {e}",
                {"error_type": type(e).__name__},
            )
        results.append(result)
    return results
