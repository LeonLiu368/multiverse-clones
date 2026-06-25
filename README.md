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

## Second module: `linear_export` (read-only)

Same pattern for **Linear**: read the GraphQL API (read-only, `LINEAR_API_KEY`) and emit the
**abundant-jira-clone `state.json`** — the ticketvector shape `tools/jira_to_state.py` produces,
served by `jira-gateway:empty` (mount your own state). Keeps **real names** (our own workspace),
unlike the anonymized jira_to_state path.

```bash
export LINEAR_API_KEY=lin_api_…
python -m spoink.linear_export --team ABT --out /tmp/linear-state.json --report /tmp/linear-report.md
```

`--team` defaults to the team with the most issues. Validate by serving it:

```bash
docker run --rm -p 8765:8765 \
  -e WORLD_ISSUES_STATE_FILE=/var/lib/ticketvector/state.json -e WORLD_ISSUES_BIND_HOST=0.0.0.0 \
  -v /tmp/linear-state.json:/var/lib/ticketvector/state.json:ro \
  ghcr.io/abundant-ai/jira-gateway:empty
# then: POST /rpc {"method":"get_issue","kwargs":{"identifier":"ABT-741"}}
```

Maps Linear → ticketvector vocab: priority int → urgent/high/medium/low/none, workflow-state
`type` → unstarted/started/completed/cancelled. `issueHistory` is accessible (verified) for the
mutable-state `slice_as_of(T)` replay — not yet wired.

## Roadmap (out of scope for these modules)

Daily scheduler · full back-history · GitHub snapshot + repo rollback ·
mutable-state `slice_as_of(T)` (history replay for trackers) · per-team / multi-team Linear ·
cross-snapshot identity continuity · email capture · write-back.
