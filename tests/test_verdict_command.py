"""Tests for the `command` check type: unverified on a broken/missing
command, OK on first run (baseline), and the NO_CHANGE -> STALE escalation
when a command's output stays identical across runs."""
from __future__ import annotations
import sys
from datetime import datetime, timedelta, timezone

from outcome_watchdog.config import Outcome
from outcome_watchdog.state import StateStore
from outcome_watchdog.checks import check_command
from outcome_watchdog.verdict import Verdict


def _python_echo(value: str) -> str:
    # Cross-platform "print a value" command using the current interpreter,
    # instead of relying on a shell builtin that may differ Windows/Unix.
    return f'{sys.executable} -c "print({value!r})"'


def test_nonexistent_command_is_unverified(tmp_path):
    outcome = Outcome(
        name="broken-cmd", type="command",
        command="this_binary_does_not_exist_anywhere_xyz --flag",
        freshness="1h", timeout=5,
    )
    state = StateStore(tmp_path / "state.json")

    result = check_command(outcome, state, datetime.now(timezone.utc))

    assert result.verdict is Verdict.UNVERIFIED
    assert not result.verdict.is_failure


def test_first_run_records_baseline(tmp_path):
    outcome = Outcome(
        name="counter", type="command", command=_python_echo("42"),
        freshness="1h", timeout=5,
    )
    state = StateStore(tmp_path / "state.json")

    result = check_command(outcome, state, datetime.now(timezone.utc))

    assert result.verdict is Verdict.OK
    assert state.get("counter")["value"] == 42.0


def test_unchanged_output_becomes_no_change_then_stale(tmp_path):
    outcome = Outcome(
        name="counter", type="command", command=_python_echo("7"),
        freshness="1h", timeout=5,
    )
    state = StateStore(tmp_path / "state.json")

    t0 = datetime.now(timezone.utc)
    check_command(outcome, state, t0)  # baseline

    # Shortly after: unchanged output, still within the freshness window.
    soon = t0 + timedelta(minutes=10)
    result_soon = check_command(outcome, state, soon)
    assert result_soon.verdict is Verdict.NO_CHANGE
    assert result_soon.verdict.is_failure

    # Much later: unchanged output for longer than the freshness window.
    later = t0 + timedelta(hours=2)
    result_later = check_command(outcome, state, later)
    assert result_later.verdict is Verdict.STALE


def test_changed_output_is_ok(tmp_path):
    state = StateStore(tmp_path / "state.json")
    t0 = datetime.now(timezone.utc)

    outcome1 = Outcome(name="counter", type="command", command=_python_echo("1"), freshness="1h", timeout=5)
    check_command(outcome1, state, t0)

    outcome2 = Outcome(name="counter", type="command", command=_python_echo("2"), freshness="1h", timeout=5)
    result = check_command(outcome2, state, t0 + timedelta(minutes=5))

    assert result.verdict is Verdict.OK
