"""Offline example: monitor accepted agent results, not attempted model calls.

After ``pip install -e .`` run ``python examples/agent_outcomes.py``.
Fixtures live in a temporary directory and are removed when the demo ends.
"""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from outcome_watchdog.config import Outcome, WatchdogConfig
from outcome_watchdog.engine import run_outcomes
from outcome_watchdog.state import StateStore


def evaluate(ledger: Path, state_path: Path, now: datetime):
    """Call the real engine with an explicit accepted-result ledger contract."""
    config = WatchdogConfig(outcomes=[Outcome(
        name="accepted-agent-results", type="log_growth", path=str(ledger),
        freshness="24h", timestamp_field="accepted_at", min_new=1,
    )])
    return run_outcomes(config, StateStore(state_path), now)[0]


def demo(directory: Path, now: datetime) -> dict:
    directory.mkdir(parents=True, exist_ok=True)
    accepted = directory / "accepted.jsonl"
    accepted.write_text(json.dumps({
        "run_id": "fixture-accepted", "accepted_at": now.isoformat(),
        "artifact": "design.json",
    }) + "\n", encoding="utf-8")
    quiet = directory / "quiet.jsonl"
    quiet.write_text(json.dumps({
        "run_id": "fixture-old", "accepted_at": (now - timedelta(days=4)).isoformat(),
        "artifact": "old-design.json",
    }) + "\n", encoding="utf-8")
    # The files were both written now. Their mtimes are fresh, but only one
    # contains a result accepted inside the expected outcome window.
    return {
        label: evaluate(path, directory / f"{label}-state.json", now).to_dict()
        for label, path in (("fresh", accepted), ("quiet", quiet),
                            ("missing", directory / "missing.jsonl"))
    }


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="agent-outcomes-") as directory:
        results = demo(Path(directory), datetime.now(timezone.utc))
        print(json.dumps({"mode": "offline-fixtures", "results": results}, indent=2))


if __name__ == "__main__":
    main()
