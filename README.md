# Slack-observability + codebase tasks (isolated, for Harbor / Oddish)

> **Branch:** `mattermost-focused-implementation`. The agent operates a realistic **Slack Web
> API** that is served by a small gateway over a real **Mattermost** backend — packaged as a
> 2-container **isolated** artifact that hides the simulation (no Mattermost/`:8065`/`/api/v4`
> tells). The from-scratch Slack clone lives on the `slack-focused-implementation` branch.

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

## Architecture (the isolated artifact)

```
   ┌──────────────────────────────── one Harbor task ────────────────────────────────┐
   │   ┌────────────────────┐         Slack Web API          ┌──────────────────────┐ │
   │   │  main (agent)      │  ───────────────────────────►  │  api  (sidecar)      │ │
   │   │                    │     http://api/api/<method>    │                      │ │
   │   │  slack CLI + MCP   │  ◄───────────────────────────  │  slackgw gateway :80 │ │
   │   │  SLACK_API_URL,    │     {"ok":true,...} Slack JSON  │     │  translates     │ │
   │   │  SLACK_BOT_TOKEN    │                                │     ▼  to /api/v4     │ │
   │   │  python+pytest     │                                │  Mattermost (real)   │ │
   │   │  /workspace = repo │   the fix-info is NOT in the   │  bound 127.0.0.1 —   │ │
   │   │  whose tests FAIL  │   repo — only in the chat      │  UNREACHABLE by agent│ │
   │   └─────────┬──────────┘                                └──────────────────────┘ │
   │             ▼  verifier: pytest (hidden grader, isolated dir) [+ comms via gateway]│
   │                /logs/verifier/reward.txt                                          │
   └───────────────────────────────────────────────────────────────────────────────────┘
```

- **`api` sidecar** — real **Mattermost** bound to `127.0.0.1` (never exposed) + a **Slack Web
  API gateway** (`slackgw`, FastAPI) on `:80`. The gateway speaks faithful Slack (`{"ok":...}`
  envelopes, `C…`/`U…` ids, `ts` strings, snake_case errors), translates to Mattermost `/api/v4`,
  validates an `xoxb-` token, and scrubs backend/framework headers. From the agent, Mattermost,
  its port, `/api/v4`, and its headers are **all invisible**.
- **`main`** — the agent: the **`slack` CLI** + the **`slack` MCP server** (the `slackcli` package),
  configured via `SLACK_API_URL` / `SLACK_BOT_TOKEN` env, plus `python`/`pytest` and the codebase at
  `/workspace`. It reaches only the neutral host `api`. No raw SDK/curl in the task instructions.
- **No `networks:` block** (Harbor injects `network_mode`, which conflicts); IP/port isolation is
  achieved by binding Mattermost to localhost inside the sidecar. Both services pin `linux/amd64`.

The whole backend (Mattermost + gateway + seeder) is **one prebuilt image**,
**`ghcr.io/abundant-ai/slack-service`**, built once from
[`selfcontained/base/`](selfcontained/base/) and **pulled** by every task's `api` service — never
rebuilt per task. The agent (`main`) is a thin `python:slim` build with the codebase, so it carries
no Mattermost tells. Reference compose: [`selfcontained/isolated/`](selfcontained/isolated/);
release process: [docs/IMAGE-RELEASE.md](docs/IMAGE-RELEASE.md).

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
- `slack search` (`search.messages`) is **noisy on purpose** — superseded + agreed values both surface.

→ Tool surface: [docs/TOOLS.md](docs/TOOLS.md) · Lifecycle/isolation: [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md)
→ Authoring: [docs/CREATING-TASKS.md](docs/CREATING-TASKS.md) · Reuse/tradeoffs: [docs/WHAT-WE-TOOK-FROM-MATTERMOST.md](docs/WHAT-WE-TOOK-FROM-MATTERMOST.md)

---

## Run it

```bash
# With Oddish
cd /path/to/oddish/oddish
uv run oddish run /path/to/this-repo/oddish/tasks -c /path/to/this-repo/oddish/sweep.yaml

# Locally, validate one task end-to-end
REGISTRY=ghcr.io/abundant-ai TAG=latest selfcontained/base/build.sh   # once: build slack-service locally
cd oddish/tasks/buried-spec/environment
docker compose up -d --build            # api PULLS slack-service (seeds); main builds thin agent
MAIN=$(docker compose ps -q main)
docker cp ../tests "$MAIN":/tests && docker cp ../solution "$MAIN":/solution
docker exec -i "$MAIN" bash /tests/run_verifier.sh     # nop    -> reward 0
docker exec -i "$MAIN" bash /solution/solve.sh
docker exec -i "$MAIN" bash /tests/run_verifier.sh     # oracle -> reward 1
docker compose down -v
```

## Repo layout
```
selfcontained/
  base/                          # SINGLE SOURCE: Dockerfile.service (the pushed image) + slackgw/ +
                                 #   seed.py + entrypoints; plus the thin agent Dockerfile, compose, vendor.sh
  isolated/                      # reference compose (api pulls slack-service, main builds thin)
.github/workflows/build-service-image.yml   # builds + pushes slack-service to GHCR on push to main
oddish/
  manifest.yaml / sweep.yaml     # the 3 tasks + agents
  tasks/<task>/                  # each: environment/ (Dockerfile [thin agent] + main-entrypoint.sh +
                                 #   docker-compose.yaml + data/ + codebase/ — NO backend build, it's pulled),
                                 #   instruction.md, solution/solve.sh, tests/{test.sh,run_verifier.sh,trusted/}
docs/                            # ENVIRONMENT, TOOLS, CREATING-TASKS, WHAT-WE-TOOK-FROM-MATTERMOST, audits/
```
