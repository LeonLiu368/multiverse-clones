# spoink — the abundant snapshot engine

Goal: a **daily snapshot engine** that captures company state (Slack, GitHub, email…)
so we can *time-travel* — slice the data back to the moment a task was created and
turn Dobby-completed tasks into hardcoded eval tests.

## First module: `slack_export` (read-only)

Pulls a few Slack channels over a recent window into the **standard Slack export
directory layout**, so `abundant-slack-clone`'s existing importer ingests it with
no new conversion code. The real deliverable is a **sufficiency report**: which API
methods/scopes the token has, coverage counts, and a go/no-go verdict.

- **Read-only.** Uses an `xoxp-` user token from `SLACK_USER_TOKEN` (never passed on
  the CLI, never logged or written). Write-back is intentionally out of scope.
- Raw `ts` is preserved end-to-end, so a later `slice_as_of(T)` is a one-line filter.

### Run

```bash
export SLACK_USER_TOKEN=xoxp-…            # from W
python -m spoink.slack_export \
  --channels "#eng,#incidents,#general" \
  --since 90d \
  --out /tmp/slack-export \
  --report /tmp/report.md
```

`--since` accepts `90d` | `12h` | `all` | `YYYY-MM-DD` (built to extend further back later).

### Validate the round-trip (reuses the clone, unmodified)

```bash
cd ../abundant-slack-clone
python -m slackclone.cli.main seed import-export /tmp/slack-export \
  --emit /tmp/seed.json --out /tmp/slack.db
```

Message count and threads/reactions should match what `spoink` reported.

### Test (no token needed)

```bash
pytest            # round-trips synthetic API responses through the clone's importer
```

## Roadmap (out of scope for this module)

Daily scheduler · full back-history · GitHub snapshot + repo rollback ·
`slice_as_of(T)` slicer · cross-snapshot identity continuity · email capture · Slack write-back.
