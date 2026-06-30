# Slack-observability + codebase tasks (isolated, for Harbor / Oddish)

> The agent operates a realistic **Slack Web API** served by a small gateway over a **SQLite
> store seeded from a real Slack export** — packaged as a **two-container agent + gateway**
> artifact. Harbor force-builds the thin `main` agent `FROM ghcr.io/abundant-ai/slack-agent`
> (a data-free image carrying ONLY the agent tools: our **`slack` CLI** and the off-the-shelf
> **[korotovsky `slack-mcp`](https://github.com/korotovsky/slack-mcp-server)** server) + the
> codebase; the workspace lives in a separate **`slack` gateway sidecar** the agent reaches only
> over HTTP — so the seeded export, the SQLite DB, and the importer are never on the agent's disk.

These are **APEX-SWE-style observability tasks**: the agent is dropped into a workspace with
**heavy, noisy Slack history** *and* a **codebase whose tests fail**, and must use its tools to
recover information that is **only** available in the chat — then fix the code so the suite
passes. One task also requires **posting a postmortem back to Slack**.

It directly measures the benchmark's core question:

> *Does the model effectively and creatively discover and use the tools at its disposal
> (MCP / CLI / API / codebase / local env) to gather information and complete difficult tasks,
> including action beyond coding (verification, deployment, communication)?*

Two properties are engineered in: **(a) the chat tool is critical** (the fix is impossible
without it) and **(b) using it is non-trivial** (the fact is buried among distractors and
*superseded* values, so a naive search returns the wrong answers).

---

## Architecture (two containers: agent + gateway)

```
   ┌──────────────────────────── one Harbor task ────────────────────────────────────┐
   │   ┌─────────────────────────────────┐      ┌──────────────────────────────────┐  │
   │   │  main  (the AGENT — thin)       │      │  slack  (the GATEWAY sidecar)    │  │
   │   │                                 │      │                                  │  │
   │   │  slack CLI ─┐                   │ HTTP │  import_export.py:               │  │
   │   │  slack-mcp ─┴──► http://slack/api/<method> ──►  /data/slack-export ► SQLite │
   │   │  python3 + pytest               │      │  slackgw gateway (:80) ◄─ SQLite  │  │
   │   │  /workspace = repo whose        │      │                                  │  │
   │   │  tests FAIL                     │      │  NO agent code; NO codebase      │  │
   │   │  NO data, NO slackgw, NO import │      │                                  │  │
   │   └────────────────┬────────────────┘      └──────────────────────────────────┘  │
   │                    ▼ verifier: pytest (hidden grader) + comms check via gateway   │
   │                      /logs/verifier/reward.txt                                    │
   └─────────────────────────────────────────────────────────────────────────────────┘
```

- **`main`** (the thing under test) — Harbor force-builds it `FROM ghcr.io/abundant-ai/slack-agent`
  (a **thin, data-free** image: only the **`slack` CLI** + the korotovsky **`slack-mcp`** binary +
  `python3`/`pytest` on a neutral `python:slim` base) and adds the codebase at `/workspace`. It holds
  **no Slack data, no gateway source (`slackgw`), no importer (`import_export.py`)** — it reaches the
  workspace only over HTTP at `$SLACK_API_URL` (`http://slack`). This is what keeps the answer key off
  the agent's disk.
- **`slack`** (the gateway sidecar) — Harbor does **not** build it; it's a pulled
  `slack-gateway:{empty|prod-v1}` image (with a `build:`+`image:` dual so it also builds + tags
  locally with no registry creds, R1.5). The **importer** loads the **mounted** `/data/slack-export`
  (a real export) into **SQLite**; the **Slack Web API gateway** (`slackgw`, FastAPI) on `:80` serves
  faithful Slack from it (`{"ok":...}` envelopes, `C…`/`U…` ids, `ts` strings, threads, reactions,
  snake_case errors). No Mattermost, no Postgres.
- **No `networks:` block** (Harbor injects `network_mode`). The agent waits on the gateway
  healthcheck via `depends_on: service_healthy`.

The gateway ships as the canonical **image trio**: `slack-service` (base, no data) →
`slack-gateway:prod-v1` (corpus DB baked in, serves mount-free) + `slack-gateway:empty` (mount
target). Release process: [docs/IMAGE-RELEASE.md](docs/IMAGE-RELEASE.md). Tests:
[tests/](tests/) (`tests/test.sh`), coverage matrix: [docs/COVERAGE.md](docs/COVERAGE.md).

---

## The tasks

| Task | Codebase problem | Buried in Slack (critical + non-trivial) | Beyond coding |
|---|---|---|---|
| **buried-spec** | `ratelimit/bucket.py` token-bucket constants are wrong | the *agreed* load-test config (CAPACITY 200→100, REFILL_RATE 15.0→**10.0** correction, OVERDRAFT 10→0) + traps | — |
| **contract-drift** | `events/publisher.py` emits the v1 event schema | the v2 schema incl. a mid-thread **`author_id`→`actor_id` correction** + float→int-ms + v1 traps | — |
| **incident-fix-report** | `budget/monitor.py::check_budget` thresholds are wrong | the agreed SLO thresholds (`>=0.05`/90%, warn `>=0.01`/75%, latency-paging) + a 0.10 trap | **post thresholds to #error-budget-reports** |

All three validated `nop=0 / oracle=1`; each also checked so a wrong-but-plausible fix still
scores **0**, and `incident-fix-report` scores 0 if the code is fixed but the notification isn't
posted (the communication is read back through the gateway).

---

## Why the tool use is genuinely required (anti-shortcut)
- The fix-critical fact is only in Slack — never in the repo or visible tests.
- Visible tests are **invariant-only**; a **hidden** `test_grade_*.py` (staged only at grade time)
  pins the exact answer.
- The verifier grades the candidate package + trusted tests in an **isolated `/tmp` dir** — editing
  `/workspace/tests` can't game it.
- search (`slack search` / MCP `conversations_search_messages`) is **noisy on purpose** —
  superseded + agreed values both surface.

→ Tool surface: [docs/TOOLS.md](docs/TOOLS.md) · Lifecycle/isolation: [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md)
→ Authoring: [docs/CREATING-TASKS.md](docs/CREATING-TASKS.md) · Real-export import: [docs/REAL-SLACK-IMPORT.md](docs/REAL-SLACK-IMPORT.md)

---

## Run it

```bash
# With Oddish
cd /path/to/oddish/oddish
uv run oddish run /path/to/this-repo/oddish/tasks -c /path/to/this-repo/oddish/sweep.yaml

# Locally, validate one task end-to-end
cd oddish/tasks/buried-spec/environment
docker compose up -d --build   # builds FROM slack-service:latest, imports the export, starts the gateway
MAIN=$(docker compose ps -q main)
# wait for healthy (import + gateway ~3s)
docker cp ../tests "$MAIN":/tests && docker cp ../solution "$MAIN":/solution
docker exec -i "$MAIN" bash /tests/run_verifier.sh     # nop    -> reward 0
docker exec -i "$MAIN" bash /solution/solve.sh
docker exec -i "$MAIN" bash /tests/run_verifier.sh     # oracle -> reward 1
docker compose down -v
```
> Local Docker on Apple Silicon: build a native image (drop `platform: linux/amd64`) — amd64
> emulation hangs. CI builds amd64 natively on `ubuntu-latest` for Modal.

## Repo layout
```
selfcontained/
  base/                          # SINGLE SOURCE: Dockerfile.service (the pushed image) + slackgw/
                                 #   (gateway + SQLite store) + import_export.py + slack_export_writer.py +
                                 #   slackcli/ (slack CLI) + mcp/ (korotovsky patch + wrapper) + entrypoints + vendor.sh
.github/workflows/build-service-image.yml   # builds + pushes slack-service to GHCR on push to main
oddish/
  manifest.yaml / sweep.yaml     # the 3 tasks + agents
  tasks/<task>/                  # each: environment/ (Dockerfile [FROM slack-service] + main-entrypoint.sh +
                                 #   docker-compose.yaml + data/{generate.py, slack-export/} + codebase/),
                                 #   instruction.md, solution/solve.sh, tests/{test.sh,run_verifier.sh,trusted/}
docs/                            # ENVIRONMENT, TOOLS, CREATING-TASKS, DATA-PIPELINE, REAL-SLACK-IMPORT, audits/
```
