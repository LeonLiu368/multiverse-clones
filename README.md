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
   │   │  curl + slack_sdk  │  ◄───────────────────────────  │  slackgw gateway :80 │ │
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
- **`main`** — the agent: `curl` + the official **`slack_sdk`**, configured the real way via
  `SLACK_API_URL` / `SLACK_BOT_TOKEN` env, plus `python`/`pytest` and the codebase at
  `/workspace`. It reaches only the neutral host `api`.
- **No `networks:` block** (Harbor injects `network_mode`, which conflicts); IP/port isolation is
  achieved by binding Mattermost to localhost inside the sidecar. Both services pin `linux/amd64`.

Canonical reference artifact: **[`selfcontained/isolated/`](selfcontained/isolated/)**. The
gateway lives in **[`slackgw/`](slackgw/)**.

---

## The tasks

| Task | Codebase problem | Buried in Slack (critical + non-trivial) | Beyond coding |
|---|---|---|---|
| **buried-spec** | `billing/fees.py::overdue_fee` unimplemented | the *agreed* fee policy — superseded proposals (grace 7→5, 2/4/6→1.5/3/5, $10→$5) + traps | — |
| **contract-drift** | `payments/charge.py` on a dead API contract | the v2 contract incl. a mid-thread **`customer_id`→`customer` correction** + v1 traps | — |
| **incident-fix-report** | `monitoring/alerts.py::should_page` unimplemented | the agreed paging policy + a **red-herring** DB hypothesis | **post a postmortem to #postmortems** |

All three validated `nop=0 / oracle=1`; each also checked so a wrong-but-plausible fix still
scores **0**, and `incident-fix-report` scores 0 if the code is fixed but the postmortem isn't
posted (the communication is read back through the gateway).

---

## Why the tool use is genuinely required (anti-shortcut)
- The fix-critical fact is only in Slack — never in the repo or visible tests.
- Visible tests are **invariant-only**; a **hidden** `test_grade_*.py` (staged only at grade time)
  pins the exact answer.
- The verifier grades the candidate package + trusted tests in an **isolated `/tmp` dir** — editing
  `/workspace/tests` can't game it.
- `slack_sdk`/`search.messages` is **noisy on purpose** — superseded + agreed values both surface.

→ Tool surface: [docs/TOOLS.md](docs/TOOLS.md) · Lifecycle/isolation: [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md)
→ Authoring: [docs/CREATING-TASKS.md](docs/CREATING-TASKS.md) · Reuse/tradeoffs: [docs/WHAT-WE-TOOK-FROM-MATTERMOST.md](docs/WHAT-WE-TOOK-FROM-MATTERMOST.md)

---

## Run it

```bash
# With Oddish
cd /path/to/oddish/oddish
uv run oddish run /path/to/this-repo/oddish/tasks -c /path/to/this-repo/oddish/sweep.yaml

# Locally, validate one task end-to-end (first build pulls Mattermost; ~5-8 min)
cd oddish/tasks/buried-spec/environment
docker compose up -d --build            # api healthy = seeded; main has baked SLACK_* env
MAIN=$(docker compose ps -q main)
docker cp ../tests "$MAIN":/tests && docker cp ../solution "$MAIN":/solution
docker exec -i "$MAIN" bash /tests/run_verifier.sh     # nop    -> reward 0
docker exec -i "$MAIN" bash /solution/solve.sh
docker exec -i "$MAIN" bash /tests/run_verifier.sh     # oracle -> reward 1
docker compose down -v
```

## Repo layout
```
slackgw/                         # the Slack Web API gateway (FastAPI) over Mattermost
selfcontained/isolated/          # canonical 2-container artifact (Dockerfile.api/main, entrypoints, compose, seed)
oddish/
  manifest.yaml / sweep.yaml     # the 3 tasks + agents
  tasks/<task>/                  # each: environment/ (flat: Dockerfile.api/main, slackgw/, seed.py, data/, codebase/),
                                 #       instruction.md, solution/solve.sh, tests/{test.sh,run_verifier.sh,trusted/}
docs/                            # ENVIRONMENT, TOOLS, CREATING-TASKS, WHAT-WE-TOOK-FROM-MATTERMOST, audits/
```
