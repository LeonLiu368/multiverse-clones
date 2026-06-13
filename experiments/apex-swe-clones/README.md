# apex-swe-clones

APEX-SWE **Observability** tasks ([mercor/APEX-SWE](https://huggingface.co/datasets/mercor/APEX-SWE),
CC-BY-4.0) re-platformed onto abundant-ai's service clones.

## Why

APEX's Observability tasks recreate a production incident with a six-container stack —
lightweight Plane (Django + Postgres + Redis), lightweight Mattermost, real Loki +
Grafana — at ~8 GB RAM / 40 GB disk and 180–240s startups per task. We keep the task
*content* and swap the *substrate* for three published, deterministic clone images:

| APEX service | Clone | Image |
|---|---|---|
| Plane (issues) | ticketvector | `ghcr.io/abundant-ai/ticketvector-service:main` |
| Mattermost (chat) | slack-service | `ghcr.io/abundant-ai/slack-service:latest` |
| Loki + Grafana + Prometheus | gauge | `ghcr.io/abundant-ai/gauge-service:main` |

**Preserved verbatim:** the upstream repo @ `base_commit` (cloned at build), the planted
bug, `solution/golden.patch`, `tests/test.patch`, `tests/test_metadata.json` (F2P/P2P),
and the incident *content* (issue text, chat thread, log lines). Grading runs the repo's
own test suite on `/app/repo` after applying `test.patch` — fully independent of the clones,
which are only the diagnostic surface.

## Layout

```
apex-swe-clones/
├── apex-swe-clones-manifest.yaml   # Oddish experiment manifest
├── tools/
│   ├── apex_to_clones.py           # converter: APEX fixtures -> clone seeds
│   └── SCHEMAS.md                  # the three clone seed schemas (authoritative)
└── tasks/<task>/
    ├── task.toml                   # mcp_servers: slack (slack-mcp), grafana (mcp-grafana)
    ├── instruction.md
    ├── environment/
    │   ├── Dockerfile              # repo base image + multi-stage COPY of clone CLIs/MCP
    │   ├── docker-compose.yaml     # main + ticketvector/slack/gauge sidecars
    │   └── data/{ticketvector,slack,gauge}/...   # converter output
    ├── solution/{golden.patch,solve.sh}
    └── tests/{test.sh,stage_data.sh,run_verifier.sh,test.patch,test_metadata.json}
```

## Recipe (convert one Observability task)

Source = an `apex-swe-variants` task (repo+patches already extracted) or the raw APEX task.

1. **Stage** the source fixtures: `data/plane/issues.json`, `data/mattermost/scraped.json`,
   `data/loki/logs.json`, plus `golden.patch`, `test.patch`, `test_metadata.json`.
2. **Convert** the diagnostic surface:
   ```
   python tools/apex_to_clones.py --from-variant <src> \
     --out tasks/<task>/environment/data \
     --workspace meridian --project-key <KEY> --service <service-name>
   ```
   Mappers: Plane issues → ticketvector `state.json` (issue assigned to `agent`);
   Mattermost → slack `scraped.json` (author flattened to a username string);
   Loki streams + Grafana → gauge `state.json` (logs become `entries[]`; gauge's
   label+`|=` filter engine serves any plausible LogQL query; `meta.now` is anchored
   just after the last log so default time windows include it).
3. **Copy** the pass-through artifacts into `solution/` and `tests/`.
4. **Author** `Dockerfile` (repo's language base image; clone `git clone` @ base_commit;
   multi-stage `COPY --from` the clone CLIs + MCP + `/opt` packages), `docker-compose.yaml`
   (copy from an existing task — the clone sidecars never change), `task.toml`,
   `instruction.md`, `solution/solve.sh` (`git apply golden.patch`), and the verifier
   scripts (`run_verifier.sh` runs the repo's own test command from `test_metadata.json`).

## Brittle hidden tests → discoverable spec (`--spec`)

Some APEX F2P tests import **exact private symbols** from the fix (e.g. paperless's
`test_lock_backoff.py` does `from documents.search._backend import _LOCK_BACKOFF_CAP, ...`).
A semantically-correct fix with different names fails at import → the task grades a correct
solution as 0 ("BAD_FAILURE – Underspecified Instruction"; only the oracle passes). The
test is hidden, so the agent cannot infer those names.

Fix without touching the test/oracle: make the contract **discoverable through the
investigation** the task is already about. `apex_to_clones.py --spec <overlay.json>` merges
a realistic on-call handoff (a tech-lead **ticket comment** naming the file, the new
exception, the constant names, and the reschedule behavior, plus a corroborating slack
line) into the seeds. The agent finds it via `linear issue view <ISSUE> --comments`. See
`tasks/paperless-ngx-12856/spec.json`. Only add a spec when a task's `test.patch` imports
new private symbols a fix can't infer (`grep -E "import .*_[A-Z]" test.patch`); behavior-based
tests (e.g. bor's) need none.

## Per-task local gate (before Oddish)

- Converter fidelity: every diagnostic fact present in the generated seeds.
- gauge: `gcx logs query '{service="<svc>"}'` (and a `|=` filter) returns the incident lines.
- ticketvector: `linear issue mine` returns the agent-assigned ticket.
- Grading: `golden.patch` + `test.patch` apply cleanly at `base_commit`.
- Full `oracle=1 / nop=0` is confirmed on Oddish (the amd64 repo build is heavy to run on
  an arm64 dev host; grading logic is identical to the proven `apex-swe-variants` tasks).

## Clone tool surface (agent)

- Issue tracker: `linear` / `jira` CLIs (`WORLD_ISSUES_*`, `PLANE_BASE_URL`).
- Chat: `slack` CLI + `slack-mcp` MCP (`SLACK_API_URL`, `SLACK_BOT_TOKEN`).
- Observability: `gcx` CLI + `mcp-grafana` MCP (`GRAFANA_URL`, `GRAFANA_TOKEN`).
  Do NOT ship `gaugectl` (admin) into the agent image.
