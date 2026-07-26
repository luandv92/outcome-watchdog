# outcome-watchdog

**Your cron job says `exit 0`. That might be a lie.**

A scheduled job — cron, Windows Task Scheduler, a CI step, an Airflow DAG —
can run to completion, log "success", and exit `0` while silently producing
**zero real output**: an empty export file, an append-only log with no new
lines, a scraper that ran but the source blocked it, a report that overwrote
itself with the same numbers as yesterday. The exit code only tells you the
process didn't crash. It never tells you the job actually did its job.

That gap is where silent failures live for days before anyone notices — and
they're always noticed the expensive way (a customer complains, a report is
missing, a backup that "ran fine for months" turns out to be empty).

`outcome-watchdog` checks the **real outcome** of a job — not its exit code —
against a config you write once. It looks at three kinds of ground truth:

- a **file** that should have been (re)written recently and actually gotten
  bigger / touched (size or mtime delta)
- an **append-only log** (e.g. a JSONL ledger) that should have gained new
  records within a time window
- a **command** whose output (a count, a status, anything) should change
  over time

## Why graduated verdicts, not pass/fail

The most important design decision in this package: a check is never
collapsed to a binary "ok" / "broken". There are four verdicts:

| Verdict      | Meaning                                                                 |
|--------------|--------------------------------------------------------------------------|
| `OK`         | Fresh, and the tracked value actually changed.                          |
| `STALE`      | Past its expected freshness window — nothing new for too long.         |
| `NO_CHANGE`  | Checked in time, but nothing changed. **This is the exit-0-lie case.** |
| `UNVERIFIED` | The check itself couldn't run (file missing, command errored, ...).    |

`UNVERIFIED` is deliberately **not** a failure. If the watchdog can't see the
outcome — the file isn't there yet, the machine running the check lost
network, permissions changed — that's an inability to look, not evidence
something is broken. Treating "couldn't check" the same as "confirmed
broken" is exactly how monitoring tools cry wolf and get ignored. Only `OK`
is fine; `STALE` and `NO_CHANGE` are the two verdicts that actually fail the
CLI's exit code.

## Install

```bash
pip install outcome-watchdog
# YAML configs need PyYAML:
pip install outcome-watchdog[yaml]
```

## Usage

```bash
outcome-watchdog check config.yml
outcome-watchdog check config.yml --json     # machine-readable report
outcome-watchdog check config.yml --state /var/lib/watchdog/state.json
```

Exit code is `0` if every outcome is `OK` or `UNVERIFIED`, non-zero if any
outcome is `STALE` or `NO_CHANGE` — so it drops straight into a cron job's
`&& mail -s alert` or a CI gate.

### Sample config (`config.yml`)

```yaml
# Optional: where to remember state between runs (defaults to a file next
# to this config). Needed for change-detection — a single run can't tell
# whether a file grew unless it remembers the previous size.
state_file: .outcome_watchdog_state.json

outcomes:
  # A nightly export job: the file should be rewritten every night AND its
  # size should change. If the job "succeeds" but writes an identical file
  # (e.g. the upstream API returned nothing new), this reports NO_CHANGE
  # instead of a false green.
  - name: nightly-export
    type: file
    path: /var/data/exports/daily.csv
    freshness: 26h        # a little slack over the 24h schedule
    change: size          # or: mtime

  # An append-only ledger (JSONL, one record per line). Counts how many
  # records have a `posted_at` timestamp inside the freshness window —
  # this is the generalized version of "did today's cron actually post
  # anything, or did it run and post zero items?"
  - name: content-publish-ledger
    type: log_growth
    path: /var/log/publisher/ledger.jsonl
    freshness: 24h
    timestamp_field: posted_at
    min_new: 1

  # Any shell command whose output should change over time — a row count,
  # a status field, a checksum. Output is compared run-over-run; unchanged
  # output only becomes STALE once it's been unchanged longer than the
  # freshness window (a single unchanged run is just NO_CHANGE, not yet
  # an alarm — this is how the tool tells "one quiet cycle" apart from
  # "actually stuck").
  - name: orders-table-growth
    type: command
    command: "psql -tAc 'select count(*) from orders' mydb"
    freshness: 15m
    timeout: 10
```

Run it:

```bash
$ outcome-watchdog check config.yml
outcome-watchdog report

🟢 OK         nightly-export — /var/data/exports/daily.csv changed (size: 118203 -> 118955)
🔴 NO_CHANGE  content-publish-ledger — /var/log/publisher/ledger.jsonl was touched recently but only 0 new record(s) in the last 24h (< 1 required) — the job ran but produced (almost) nothing new
⚪ UNVERIFIED orders-table-growth — could not run command: [Errno 2] No such file or directory: 'psql'

3 outcome(s) checked — 1 confirmed problem(s), 1 unverified (inconclusive, not a failure)
```

Exit code is `1` because of the `NO_CHANGE` — the `UNVERIFIED` check (no
`psql` on this machine) does not, by itself, fail the run.

### `--json` output

```bash
$ outcome-watchdog check config.yml --json
```

```json
{
  "results": [
    {
      "name": "nightly-export",
      "verdict": "OK",
      "message": "/var/data/exports/daily.csv changed (size: 118203 -> 118955)",
      "details": {"path": "/var/data/exports/daily.csv", "age_seconds": 612.4, "size": 118955}
    }
  ]
}
```

## Design origin

This package generalizes a pattern from a production watchdog that has been
running for months across a couple dozen scheduled jobs: check the ledger,
not the log line; check whether anyone actually saw the output, not just
whether it was produced; never let a check's own failure become a false
alarm. The business-specific bits (what the jobs actually do) stayed behind
— what's here is the reusable shape: graduated verdicts, ground-truth checks
over exit codes, and fail-open behavior when the checker itself can't see.

## License

MIT — see [LICENSE](LICENSE).
