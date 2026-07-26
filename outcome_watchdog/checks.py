"""The three check implementations.

Each function takes an `Outcome` (parsed config), a `StateStore` (memory of
past runs), and `now`, and returns an `OutcomeResult`. All three follow the
same shape of decision:

  1. Can we even observe the outcome? If not -> UNVERIFIED. Never guess.
  2. Is it past its freshness window? -> STALE.
  3. Did the tracked value actually change since we last looked? If not
     -> NO_CHANGE. This is the "exit 0 but did nothing" case.
  4. Otherwise -> OK, and remember the new value for next time.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .config import Outcome
from .durations import parse_duration
from .state import StateStore
from .verdict import OutcomeResult, Verdict


def _now_iso(now: datetime) -> str:
    return now.astimezone(timezone.utc).isoformat()


def _parse_ts(value) -> datetime | None:
    if value is None:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def check_file(outcome: Outcome, state: StateStore, now: datetime) -> OutcomeResult:
    path = Path(outcome.path)
    if not path.exists():
        return OutcomeResult(
            outcome.name, Verdict.UNVERIFIED,
            f"path does not exist: {path}",
            {"path": str(path)},
        )
    try:
        st = path.stat()
    except OSError as e:
        return OutcomeResult(
            outcome.name, Verdict.UNVERIFIED,
            f"could not stat {path}: {e}",
            {"path": str(path)},
        )

    mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
    age = now.astimezone(timezone.utc) - mtime
    freshness = parse_duration(outcome.freshness)
    current_value = st.st_size if outcome.change == "size" else st.st_mtime

    prev = state.get(outcome.name)
    details = {
        "path": str(path),
        "age_seconds": round(age.total_seconds(), 1),
        "freshness_seconds": freshness.total_seconds(),
        outcome.change: current_value,
    }

    if age > freshness:
        verdict = Verdict.STALE
        message = (
            f"{path} last modified {age} ago, past the {outcome.freshness} freshness window"
        )
    elif prev is None:
        verdict = Verdict.OK
        message = f"{path} is fresh; recording baseline {outcome.change}={current_value}"
    elif prev.get("value") == current_value:
        verdict = Verdict.NO_CHANGE
        message = (
            f"{path} was touched recently but its {outcome.change} did not change "
            f"(still {current_value}) — the job ran but produced nothing new"
        )
    else:
        verdict = Verdict.OK
        message = f"{path} changed ({outcome.change}: {prev.get('value')} -> {current_value})"

    state.set(outcome.name, {"value": current_value, "checked_at": _now_iso(now)})
    return OutcomeResult(outcome.name, verdict, message, details)


def _iter_lines(path: Path) -> list[str]:
    return [ln for ln in path.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]


def check_log_growth(outcome: Outcome, state: StateStore, now: datetime) -> OutcomeResult:
    path = Path(outcome.path)
    if not path.exists():
        return OutcomeResult(
            outcome.name, Verdict.UNVERIFIED,
            f"path does not exist: {path}",
            {"path": str(path)},
        )
    try:
        st = path.stat()
        lines = _iter_lines(path)
    except OSError as e:
        return OutcomeResult(
            outcome.name, Verdict.UNVERIFIED,
            f"could not read {path}: {e}",
            {"path": str(path)},
        )

    now_utc = now.astimezone(timezone.utc)
    mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
    age = now_utc - mtime
    freshness = parse_duration(outcome.freshness)
    total_lines = len(lines)
    details: dict = {"path": str(path), "total_lines": total_lines,
                      "age_seconds": round(age.total_seconds(), 1)}

    if outcome.timestamp_field:
        new_in_window = 0
        for ln in lines:
            try:
                record = json.loads(ln)
            except Exception:
                continue
            ts = _parse_ts(record.get(outcome.timestamp_field))
            if ts is not None and (now_utc - ts) <= freshness:
                new_in_window += 1
        details["new_records_in_window"] = new_in_window
        details["min_new_required"] = outcome.min_new

        if new_in_window >= outcome.min_new:
            verdict = Verdict.OK
            message = (
                f"{path}: {new_in_window} new record(s) within the last "
                f"{outcome.freshness} (>= {outcome.min_new} required)"
            )
        elif age > freshness:
            verdict = Verdict.STALE
            message = (
                f"{path} not modified in {age}, past the {outcome.freshness} window, "
                f"and only {new_in_window} qualifying record(s) found"
            )
        else:
            verdict = Verdict.NO_CHANGE
            message = (
                f"{path} was touched recently but only {new_in_window} new record(s) "
                f"in the last {outcome.freshness} (< {outcome.min_new} required) — "
                "the job ran but produced (almost) nothing new"
            )
        state.set(outcome.name, {"value": total_lines, "checked_at": _now_iso(now)})
        return OutcomeResult(outcome.name, verdict, message, details)

    # No timestamp field configured: fall back to a pure line-count delta
    # across runs of this tool (needs at least two runs to detect NO_CHANGE).
    prev = state.get(outcome.name)
    if age > freshness:
        verdict = Verdict.STALE
        message = f"{path} not modified in {age}, past the {outcome.freshness} window"
    elif prev is None:
        verdict = Verdict.OK
        message = f"{path} is fresh; recording baseline line count {total_lines}"
    elif total_lines <= prev.get("value", -1):
        verdict = Verdict.NO_CHANGE
        message = (
            f"{path} was touched recently but its line count did not grow "
            f"(still {total_lines}) — the job ran but appended nothing new"
        )
    else:
        verdict = Verdict.OK
        message = f"{path} grew ({prev.get('value')} -> {total_lines} lines)"

    state.set(outcome.name, {"value": total_lines, "checked_at": _now_iso(now)})
    return OutcomeResult(outcome.name, verdict, message, details)


def _command_value(stdout: str) -> object:
    """Turn a command's stdout into a comparable value: the last non-empty
    line as a float if it parses as one, otherwise a hash of the full output
    (so non-numeric output can still be compared for equality across runs)."""
    lines = [ln for ln in stdout.splitlines() if ln.strip()]
    last = lines[-1].strip() if lines else ""
    try:
        return float(last)
    except ValueError:
        return hashlib.sha256(stdout.encode("utf-8", "replace")).hexdigest()


def check_command(outcome: Outcome, state: StateStore, now: datetime) -> OutcomeResult:
    try:
        proc = subprocess.run(
            outcome.command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=outcome.timeout,
        )
    except subprocess.TimeoutExpired:
        return OutcomeResult(
            outcome.name, Verdict.UNVERIFIED,
            f"command timed out after {outcome.timeout}s: {outcome.command}",
            {"command": outcome.command},
        )
    except OSError as e:
        return OutcomeResult(
            outcome.name, Verdict.UNVERIFIED,
            f"could not run command: {e}",
            {"command": outcome.command},
        )

    if proc.returncode != 0:
        return OutcomeResult(
            outcome.name, Verdict.UNVERIFIED,
            f"command exited {proc.returncode}, could not verify outcome: "
            f"{proc.stderr.strip()[:200]}",
            {"command": outcome.command, "returncode": proc.returncode},
        )

    current_value = _command_value(proc.stdout)
    freshness = parse_duration(outcome.freshness)
    now_utc = now.astimezone(timezone.utc)
    prev = state.get(outcome.name)
    details = {"command": outcome.command, "value": current_value}

    if prev is None:
        state.set(outcome.name, {"value": current_value, "changed_at": _now_iso(now)})
        return OutcomeResult(
            outcome.name, Verdict.OK,
            f"command ran; recording baseline value {current_value}",
            details,
        )

    if prev.get("value") == current_value:
        changed_at = _parse_ts(prev.get("changed_at")) or now_utc
        age = now_utc - changed_at
        details["unchanged_for_seconds"] = round(age.total_seconds(), 1)
        if age > freshness:
            verdict = Verdict.STALE
            message = (
                f"command output unchanged ({current_value}) for {age}, "
                f"past the {outcome.freshness} freshness window"
            )
        else:
            verdict = Verdict.NO_CHANGE
            message = f"command ran but its output did not change (still {current_value})"
        # keep changed_at as-is; only refresh the "last checked" bookkeeping
        state.set(outcome.name, {"value": prev.get("value"), "changed_at": prev.get("changed_at")})
        return OutcomeResult(outcome.name, verdict, message, details)

    state.set(outcome.name, {"value": current_value, "changed_at": _now_iso(now)})
    return OutcomeResult(
        outcome.name, Verdict.OK,
        f"command output changed ({prev.get('value')} -> {current_value})",
        details,
    )
