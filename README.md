# Slack-observability + codebase tasks (for Harbor / Oddish)

> **Branch:** `mattermost-focused-implementation`. The agent operates a real (seeded) Slack
> workspace through a **`slack`** tool (CLI + MCP) that is a thin facade over a real Mattermost
> backend. (The from-scratch Slack clone lives on the `slack-focused-implementation` branch.)

This repo holds **APEX-SWE-style observability tasks**: the agent is dropped into a workspace
with **heavy, noisy Slack history** *and* a **codebase whose tests are failing**, and must use
its tools to recover information that is **only** available in the chat — then fix the code so
the suite passes. One task also requires **posting a postmortem back to Slack**.

It directly measures the benchmark's core question:

> *Does the model effectively and creatively discover and use the tools at its disposal
> (MCP / CLI / API / codebase / local env) to gather information and complete difficult tasks,
> including action beyond coding (verification, deployment, communication)?*

Every task is built so that **(a) the chat tool is critical** — the fix is impossible without
it — and **(b) using it is non-trivial** — the needed fact is buried among distractors and
superseded values, so a naive keyword search returns the *wrong* answers.

---

## In one picture

```
   ┌────────────────────────────── one Harbor task ──────────────────────────────┐
   │   ┌────────────────────┐        HTTP (REST)        ┌────────────────────┐     │
   │   │  client (agent)    │ ───────────────────────►  │  mattermost        │     │
   │   │                    │   http://mattermost:8065  │  (real product)    │     │
   │   │  tool: `slack`     │ ◄───────────────────────  │  seeded with ~500  │     │
   │   │   • slack CLI      │                           │  noisy messages;   │     │
   │   │   • slack MCP      │                           │  the key fact is   │     │
   │   │                    │                           │  buried in there   │     │
   │   │  /workspace = a    │                           └────────────────────┘     │
   │   │  codebase whose    │   the fix info is NOT in the repo — only in chat      │
   │   │  pytest suite      │                                                       │
   │   │  is FAILING        │   verifier: restore trusted tests + a HIDDEN grader,  │
   │   └─────────┬──────────┘   run pytest in an isolated dir, score 0/1            │
   │             ▼  /logs/verifier/reward.txt        (incident task also checks a   │
   │                                                  postmortem was posted to Slack)│
   └───────────────────────────────────────────────────────────────────────────────┘
```

Two containers: **`mattermost`** (the chat backend, seeded with heavy synthetic history) and
**`client`** (where the agent runs — it has the `slack` tool, python+pytest, and the codebase at
`/workspace`). The agent can only reach the chat through `slack`, and the fix-critical fact is
never on disk — so the verifier's result genuinely reflects whether the agent used its tools.

---

## The tasks

| Task | The codebase problem | What's buried in Slack (critical + non-trivial) | Beyond coding |
|---|---|---|---|
| **buried-spec** | `billing/fees.py::overdue_fee` unimplemented; suite fails | the *agreed* fee policy (grace, tiers, min, cap, rounding) — with **superseded** proposals (grace 7→5, 2/4/6→1.5/3/5, $10→$5) and off-channel traps | — |
| **contract-drift** | `payments/charge.py` targets a deprecated API contract | the **v2 contract** (field names, integer cents, version, required `idempotency_key`) — incl. a mid-thread **`customer_id`→`customer` correction** and v1 traps | — |
| **incident-fix-report** | `monitoring/alerts.py::should_page` unimplemented after a pager-fatigue incident | the agreed **paging policy** (≥3 consecutive breaches at ≥5%, fast-path ≥25%) — with a **red-herring** DB hypothesis and the old thresholds as traps | **post a root-cause postmortem to #postmortems** |

All three are validated `nop=0 / oracle=1`. Each is also checked so a **wrong-but-plausible** fix
(one that satisfies the visible invariant tests, or uses a *superseded* value) still scores **0**,
and `incident-fix-report` scores 0 if the code is fixed but the postmortem isn't posted.

→ How to author another one: **[docs/CREATING-TASKS.md](docs/CREATING-TASKS.md)** (and the
`slack-observability-task-builder` skill).

---

## Why the tool use is genuinely required (anti-shortcut design)

- **The fix-critical fact is only in Slack** — never in the repo, README, or visible tests.
- **Visible tests are invariant-only** (non-negativity, monotonicity, shape) — they do *not*
  encode the policy/contract, so the agent can't read the answer from them.
- **A hidden grading test pins the exact answer.** It lives in `tests/trusted/` and is staged by
  the verifier **only at grade time** (named `test_grade_*.py` so pytest actually collects it).
- **The verifier grades in an isolated, verifier-owned dir** — it copies the candidate's package
  + the trusted tests into `/tmp` and runs there, so editing/deleting `/workspace/tests` can't
  game it (verified by a tamper test).
- **Search is noisy on purpose.** `slack search.messages "overdue fee"` returns the superseded
  *and* the agreed values; the agent has to read and disambiguate, not grep one magic word.

→ Full reuse inventory + tradeoffs: **[docs/WHAT-WE-TOOK-FROM-MATTERMOST.md](docs/WHAT-WE-TOOK-FROM-MATTERMOST.md)**
→ The `slack` tool surface (CLI methods + MCP): **[docs/TOOLS.md](docs/TOOLS.md)**
→ Lifecycle / containers / seeding / verifiers: **[docs/ENVIRONMENT.md](docs/ENVIRONMENT.md)**
→ Example QA report: **[docs/audits/buried-spec-audit.md](docs/audits/buried-spec-audit.md)**

---

## Run it

```bash
# With Oddish
cd /path/to/oddish/oddish
uv run oddish run /path/to/this-repo/oddish/tasks -c /path/to/this-repo/oddish/sweep.yaml

# Locally, validate one task end-to-end (first build pulls Mattermost; ~5-8 min)
cd oddish/tasks/buried-spec/environment
docker compose up -d --build            # mattermost healthy + ~500-msg seed; codebase at /workspace
docker cp ../tests client:/tests && docker cp ../solution client:/solution
docker compose exec -T client bash /tests/run_verifier.sh    # nop    -> reward 0 (suite failing)
docker compose exec -T client bash /solution/solve.sh
docker compose exec -T client bash /tests/run_verifier.sh    # oracle -> reward 1
docker compose down -v
```

## Repo layout

```
oddish/
  manifest.yaml / sweep.yaml      # the 3 tasks + agents
  tasks/
    buried-spec/         ┐  each a self-contained Harbor task:
    contract-drift/      ├   environment/ (mattermost service + `slack` facade + codebase/ +
    incident-fix-report/ ┘   heavy data/) · instruction.md · solution/solve.sh ·
                             tests/{test.sh,run_verifier.sh,trusted/}  (trusted/ holds the
                             canonical tests + the HIDDEN test_grade_*.py)
docs/  ENVIRONMENT.md · WHAT-WE-TOOK-FROM-MATTERMOST.md · TOOLS.md · CREATING-TASKS.md · audits/
```
