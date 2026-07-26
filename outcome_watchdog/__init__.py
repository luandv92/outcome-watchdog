"""outcome-watchdog — catches automations that exit 0 but did nothing.

A cron job, scheduled task, or CI step can run to completion, log "success",
and exit 0 while silently producing zero real-world output — an empty file,
a log with no new lines, a database query that returns the same count it did
yesterday. Exit codes only tell you the process didn't crash; they never tell
you the job actually did its job.

This package checks the real OUTCOME of a job: did the expected file/log/
command actually change, and was that change recent enough? Verdicts are
graduated (OK / STALE / NO_CHANGE / UNVERIFIED) instead of a binary pass/fail,
because a check that itself fails to run (missing file, unreachable command)
must never be reported as a confirmed failure — only as inconclusive.
"""

from .verdict import Verdict, OutcomeResult
from .config import Outcome, WatchdogConfig, load_config
from .engine import run_outcomes

__version__ = "0.1.0"

__all__ = [
    "Verdict",
    "OutcomeResult",
    "Outcome",
    "WatchdogConfig",
    "load_config",
    "run_outcomes",
    "__version__",
]
