"""Tests for the `log_growth` check type: the timestamp_field mode (count
records with a timestamp inside the freshness window) and the plain
line-count-delta fallback mode."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from outcome_watchdog.config import Outcome
from outcome_watchdog.state import StateStore
from outcome_watchdog.checks import check_log_growth
from outcome_watchdog.verdict import Verdict


def _write_ledger(path, records):
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")


def test_no_new_records_in_window_is_no_change(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    old_ts = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    _write_ledger(ledger, [
        {"id": 1, "posted_at": old_ts},
        {"id": 2, "posted_at": old_ts},
    ])

    outcome = Outcome(
        name="ledger", type="log_growth", path=str(ledger),
        freshness="24h", timestamp_field="posted_at", min_new=1,
    )
    state = StateStore(tmp_path / "state.json")

    result = check_log_growth(outcome, state, datetime.now(timezone.utc))

    assert result.verdict is Verdict.NO_CHANGE
    assert result.details["new_records_in_window"] == 0


def test_new_record_in_window_is_ok(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    old_ts = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    fresh_ts = datetime.now(timezone.utc).isoformat()
    _write_ledger(ledger, [
        {"id": 1, "posted_at": old_ts},
        {"id": 2, "posted_at": fresh_ts},
    ])

    outcome = Outcome(
        name="ledger", type="log_growth", path=str(ledger),
        freshness="24h", timestamp_field="posted_at", min_new=1,
    )
    state = StateStore(tmp_path / "state.json")

    result = check_log_growth(outcome, state, datetime.now(timezone.utc))

    assert result.verdict is Verdict.OK
    assert result.details["new_records_in_window"] == 1


def test_missing_ledger_is_unverified(tmp_path):
    outcome = Outcome(
        name="ledger", type="log_growth", path=str(tmp_path / "nope.jsonl"),
        freshness="24h", timestamp_field="posted_at",
    )
    state = StateStore(tmp_path / "state.json")

    result = check_log_growth(outcome, state, datetime.now(timezone.utc))

    assert result.verdict is Verdict.UNVERIFIED
    assert not result.verdict.is_failure


def test_line_count_delta_fallback_detects_growth(tmp_path):
    ledger = tmp_path / "plain.log"
    ledger.write_text("line one\n")

    outcome = Outcome(name="plain-log", type="log_growth", path=str(ledger), freshness="1h")
    state = StateStore(tmp_path / "state.json")

    first = check_log_growth(outcome, state, datetime.now(timezone.utc))
    assert first.verdict is Verdict.OK  # baseline

    ledger.write_text("line one\nline two\n")
    second = check_log_growth(outcome, state, datetime.now(timezone.utc))
    assert second.verdict is Verdict.OK

    # No growth on the third check -> NO_CHANGE
    third = check_log_growth(outcome, state, datetime.now(timezone.utc))
    assert third.verdict is Verdict.NO_CHANGE
