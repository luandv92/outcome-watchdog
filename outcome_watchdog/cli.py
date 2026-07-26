"""outcome-watchdog CLI.

    outcome-watchdog check config.yml
    outcome-watchdog check config.yml --json
    outcome-watchdog check config.yml --state /path/to/state.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .config import ConfigError, load_config
from .engine import run_outcomes
from .state import StateStore
from .verdict import OutcomeResult, Verdict


def _default_state_path(config_path: Path, configured: str | None) -> Path:
    if configured:
        p = Path(configured)
        return p if p.is_absolute() else (config_path.parent / p)
    return config_path.parent / f".{config_path.stem}.outcome_watchdog_state.json"


def _human_report(results: list[OutcomeResult]) -> str:
    lines = ["outcome-watchdog report", ""]
    for r in results:
        lines.append(f"{r.verdict.emoji} {r.verdict.value:<10} {r.name} — {r.message}")
    failing = [r for r in results if r.verdict.is_failure]
    unverified = [r for r in results if r.verdict is Verdict.UNVERIFIED]
    lines.append("")
    lines.append(
        f"{len(results)} outcome(s) checked — "
        f"{len(failing)} confirmed problem(s), "
        f"{len(unverified)} unverified (inconclusive, not a failure)"
    )
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="outcome-watchdog",
        description=(
            "Catches automations that exit 0 but did nothing. Checks the real "
            "outcome of a job (a file, an append-only log, or a command) "
            "instead of trusting its exit code."
        ),
    )
    parser.add_argument("--version", action="version", version=f"outcome-watchdog {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)

    check = sub.add_parser("check", help="run all configured outcome checks")
    check.add_argument("config", help="path to a YAML or JSON config file")
    check.add_argument(
        "--state",
        default=None,
        help="path to the state file used for change-detection between runs "
             "(default: alongside the config file)",
    )
    check.add_argument("--json", action="store_true", help="print a machine-readable JSON report")
    return parser


def main(argv: list[str] | None = None) -> int:
    # Some terminals (notably the classic Windows console, cp1252) can't
    # encode the emoji used in the human report. Fall back to replacing
    # unencodable characters instead of crashing the whole report.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass

    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.cmd == "check":
        return _run_check(args)

    parser.print_help()
    return 2


def _run_check(args: argparse.Namespace) -> int:
    config_path = Path(args.config)
    try:
        config = load_config(config_path)
    except ConfigError as e:
        print(f"outcome-watchdog: config error: {e}", file=sys.stderr)
        return 2

    state_path = _default_state_path(config_path, args.state or config.state_file)
    state = StateStore(state_path)

    results = run_outcomes(config, state)
    state.save()

    if args.json:
        print(json.dumps({"results": [r.to_dict() for r in results]}, indent=2))
    else:
        print(_human_report(results))

    return 1 if any(r.verdict.is_failure for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
