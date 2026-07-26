"""Tests for config loading (JSON, no PyYAML dependency needed) and the
end-to-end CLI exit-code contract: 0 when clean, non-zero when a STALE or
NO_CHANGE verdict is confirmed, and never triggered by UNVERIFIED alone."""
from __future__ import annotations

import json
import os
import time

from outcome_watchdog.cli import main
from outcome_watchdog.config import ConfigError, load_config


def test_load_json_config(tmp_path):
    cfg_path = tmp_path / "config.json"
    target = tmp_path / "data.txt"
    target.write_text("hello")
    cfg_path.write_text(json.dumps({
        "outcomes": [
            {"name": "a-file", "type": "file", "path": str(target), "freshness": "1h"},
        ]
    }))

    config = load_config(cfg_path)

    assert len(config.outcomes) == 1
    assert config.outcomes[0].name == "a-file"
    assert config.outcomes[0].type == "file"


def test_duplicate_names_rejected(tmp_path):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({
        "outcomes": [
            {"name": "dup", "type": "file", "path": "/tmp/a"},
            {"name": "dup", "type": "file", "path": "/tmp/b"},
        ]
    }))

    try:
        load_config(cfg_path)
        assert False, "expected ConfigError"
    except ConfigError:
        pass


def test_unknown_type_rejected(tmp_path):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({
        "outcomes": [{"name": "bad", "type": "not-a-real-type", "path": "/tmp/a"}]
    }))

    try:
        load_config(cfg_path)
        assert False, "expected ConfigError"
    except ConfigError:
        pass


def test_cli_exit_code_zero_when_ok(tmp_path, capsys):
    target = tmp_path / "export.csv"
    target.write_text("fresh")
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({
        "outcomes": [
            {"name": "export", "type": "file", "path": str(target), "freshness": "1h"},
        ]
    }))

    code = main(["check", str(cfg_path)])

    assert code == 0


def test_cli_exit_code_nonzero_when_stale(tmp_path, capsys):
    target = tmp_path / "export.csv"
    target.write_text("old")
    old_time = time.time() - 3 * 3600
    os.utime(target, (old_time, old_time))
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({
        "outcomes": [
            {"name": "export", "type": "file", "path": str(target), "freshness": "1h"},
        ]
    }))

    code = main(["check", str(cfg_path)])

    assert code == 1


def test_cli_exit_code_zero_when_only_unverified(tmp_path, capsys):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({
        "outcomes": [
            {"name": "missing", "type": "file", "path": str(tmp_path / "nope.txt"), "freshness": "1h"},
        ]
    }))

    code = main(["check", str(cfg_path)])

    assert code == 0
