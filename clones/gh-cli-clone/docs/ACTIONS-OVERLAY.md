# Seeded GitHub Actions overlay

`gh run view`, `gh run view --log[-failed]`, `gh pr checks`, and `gh workflow view`
need GitHub-shaped **runs → jobs → steps → logs → check-runs**. Forgejo's Actions
REST surface cannot serve that shape — `/actions/runs/*`, `/actions/jobs/*/logs`,
`/actions/workflows` all return 404, and the web log route needs a CSRF session —
and a live `act_runner` is non-deterministic. So for **read-only CI-diagnosis
tasks** the world ships a per-repo JSON seed and the CLI renders these commands
from it, byte-for-byte like real `gh`.

This is independent of the **execution** path: tasks that must actually *run* a
workflow still use `act_runner` + `gh workflow run` + `gh run watch` + `gh run
download`. The overlay only backs the read commands, and only when a seed exists
for the repo; otherwise every command falls back to the live forge.

## What it backs

| Command | Source when a seed covers the repo |
| --- | --- |
| `gh run list` | seeded runs, newest first (gh columns + TSV split) |
| `gh run view [<id>]` | run summary + `JOBS` (steps with `-v`), `ANNOTATIONS`, footer |
| `gh run view --log` / `--log-failed` | `jobName⇥stepName⇥logline` per line |
| `gh run view --job <id>` | scope view/logs to one job |
| `gh run view --json <fields>` | gh's run fields incl. nested `jobs[].steps[]` |
| `gh run view --exit-status` | non-zero exit if the run failed |
| `gh pr checks [<n>|<branch>]` | one check per job; exit 1 (fail) / 8 (pending); `--json bucket,…` |
| `gh workflow list` / `view` (`--yaml`) | seeded workflows + recent runs |

The same data is exposed over MCP (`run_list`, `run_view`, `run_log`, `pr_checks`,
`workflow_list`) so agents driving the forge headlessly get identical results.

## Pointing the CLI at a seed

The seed path is resolved, in order, from:

1. `GH_ACTIONS_SEED` or `GHC_ACTIONS_SEED` (explicit path)
2. `/run/secrets/actions-seed.json`
3. `/shared/actions-seed.json`
4. `/etc/ghc/actions-seed.json`

For a sidecar/task container, drop the file at one of the fallback paths (no env
needed) or set `GH_ACTIONS_SEED`. The overlay is read-only and never mutated.

## Seed schema

Everything except a repo key and a run id/number is optional and defaulted
(status/conclusion are derived from the jobs/steps when omitted; step numbers are
auto-assigned; durations come from the timestamps). See `examples/actions-seed.json`
for a complete, realistic failing-CI fixture.

```json
{
  "repos": {
    "OWNER/REPO": {
      "workflows": [
        {"id": 161335, "name": "CI", "path": ".github/workflows/ci.yml", "state": "active", "yaml": "..."}
      ],
      "runs": [
        {
          "id": 1402100128, "number": 128, "workflow": "CI",
          "title": "fix: make webhook retry idempotent",
          "event": "pull_request", "status": "completed", "conclusion": "failure",
          "branch": "fix/webhook-retry-idempotency", "sha": "7d3c9af…",
          "actor": "priya-n",
          "created_at": "2026-06-23T15:41:02Z",
          "started_at": "2026-06-23T15:41:10Z",
          "updated_at": "2026-06-23T15:44:58Z",
          "url": "https://github.com/OWNER/REPO/actions/runs/1402100128",
          "annotations": [
            {"level": "failure", "message": "Process completed with exit code 1.",
             "job": "test", "path": ".github", "line": 1}
          ],
          "jobs": [
            {
              "id": 4310092, "name": "test", "conclusion": "failure", "required": true,
              "started_at": "2026-06-23T15:41:12Z", "completed_at": "2026-06-23T15:44:50Z",
              "steps": [
                {"name": "Set up job", "conclusion": "success"},
                {"name": "Run pytest", "conclusion": "failure", "log": "…pytest output…\n"},
                {"name": "Upload coverage", "conclusion": "skipped"}
              ]
            }
          ]
        }
      ]
    }
  }
}
```

### Field notes

- **Derivation.** Omit a run's `status`/`conclusion` and they are inferred from
  the jobs; omit a job's and they are inferred from its steps. A failing step ⇒
  failing job ⇒ failing run.
- **`required`** (job) — surfaces in `gh pr checks --required` and the `--json`
  output. **`annotations`** (run) — rendered under the `ANNOTATIONS` section and
  drive nothing else. **`yaml`** (workflow) — returned by `gh workflow view --yaml`.
- **Status glyphs / buckets** follow gh exactly: `✓` success, `X` failure/timed-out,
  `-` skipped/cancelled/neutral, `*` in-progress; `pr checks` buckets are
  `pass|fail|pending|skipping|cancel`.
- **Durations** print in Go's `time.Duration` shape (`32s`, `1m18s`, `1h2m3s`).
- **Realism.** Logs and titles are task-authored prod content — keep them free of
  any synthetic/meta markers, exactly like the rest of the world's state.

## Why this design

- **Deterministic** — same seed ⇒ same bytes every run; no flaky act_runner timing.
- **Decoupled** — does not depend on Forgejo exposing GitHub's Actions API.
- **Offline & cheap** — a JSON file; no extra container, no network.
- **gh-exact** — `--json` field sets match real `gh` (`run view`, `pr checks`),
  output is rendered with plain `print()` so piped bytes never soft-wrap.
