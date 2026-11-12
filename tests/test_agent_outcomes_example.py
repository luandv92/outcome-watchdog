"""The example checks accepted-result time, rather than fresh log-file writes."""
import importlib.util
from datetime import datetime, timezone
from pathlib import Path

_path = Path(__file__).parents[1] / "examples" / "agent_outcomes.py"
_spec = importlib.util.spec_from_file_location("agent_outcomes", _path)
example = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(example)


def test_demo_distinguishes_fresh_quiet_and_unobservable(tmp_path):
    results = example.demo(tmp_path, datetime(2026, 11, 11, 12, tzinfo=timezone.utc))
    assert results["fresh"]["verdict"] == "OK"
    assert results["quiet"]["verdict"] == "NO_CHANGE"
    assert results["quiet"]["details"]["new_records_in_window"] == 0
    assert results["missing"]["verdict"] == "UNVERIFIED"
