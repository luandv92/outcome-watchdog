"""Tests for the `file` check type: freshness (STALE), change-detection
(NO_CHANGE via unchanged size), the happy path (OK), and UNVERIFIED for a
missing path. Uses tmp_path — no production paths involved."""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone

from outcome_watchdog.config import Outcome
from outcome_watchdog.state import StateStore
from outcome_watchdog.checks import check_file
from outcome_watchdog.verdict import Verdict


def _outcome(path, **kw):
    return Outcome(name="test-file", type="file", path=str(path), freshness=kw.pop("freshness", "1h"), **kw)


def test_missing_file_is_unverified(tmp_path):
    outcome = _outcome(tmp_path / "does-not-exist.txt")
    state = StateStore(tmp_path / "state.json")

    result = check_file(outcome, state, datetime.now(timezone.utc))

    assert result.verdict is Verdict.UNVERIFIED
    assert not result.verdict.is_failure


def test_stale_file_past_freshness_window(tmp_path):
    f = tmp_path / "export.csv"
    f.write_text("a,b,c\n1,2,3\n")
    old_time = time.time() - 3 * 3600  # 3 hours ago
    os.utime(f, (old_time, old_time))

    outcome = _outcome(f, freshness="1h")
    state = StateStore(tmp_path / "state.json")

    result = check_file(outcome, state, datetime.now(timezone.utc))

    assert result.verdict is Verdict.STALE
    assert result.verdict.is_failure


def test_first_run_is_ok_baseline(tmp_path):
    f = tmp_path / "export.csv"
    f.write_text("fresh content")

    outcome = _outcome(f, freshness="1h")
    state = StateStore(tmp_path / "state.json")

    result = check_file(outcome, state, datetime.now(timezone.utc))

    assert result.verdict is Verdict.OK
    # state must now remember this run's size for next time
    assert state.get("test-file") is not None


def test_unchanged_size_is_no_change(tmp_path):
    f = tmp_path / "export.csv"
    f.write_text("same content every time")

    outcome = _outcome(f, freshness="1h")
    state = StateStore(tmp_path / "state.json")

    first = check_file(outcome, state, datetime.now(timezone.utc))
    assert first.verdict is Verdict.OK

    # File "runs again" but writes byte-identical content (mtime bumps,
    # size doesn't) — the classic exit-0-but-did-nothing case.
    f.write_text("same content every time")
    second = check_file(outcome, state, datetime.now(timezone.utc))

    assert second.verdict is Verdict.NO_CHANGE
    assert second.verdict.is_failure


def test_changed_size_is_ok(tmp_path):
    f = tmp_path / "export.csv"
    f.write_text("v1")

    outcome = _outcome(f, freshness="1h")
    state = StateStore(tmp_path / "state.json")

    check_file(outcome, state, datetime.now(timezone.utc))
    f.write_text("v1 plus much more new content")
    result = check_file(outcome, state, datetime.now(timezone.utc))

    assert result.verdict is Verdict.OK
