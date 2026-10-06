# APEX-SWE → Harbor (clone stack): how the conversion works

Plain-English explanation of how we turn a `mercor/APEX-SWE` **Observability** task into a
Harbor task that runs on abundant-ai's service **clones**, and what changes in the process.

## What an APEX-SWE Observability task is

A real upstream repo (paperless-ngx, 0xPolygon/bor, …) frozen just before a bug-fix PR, plus
a "production incident world" the agent investigates:

- a **Plane** issue tracker (the project's issue history),
- a **Mattermost / Matrix** team chat (community discussion),
- **Loki + Grafana** logs/dashboards (the service's request logs),
- the **repo** itself (the buggy code), and
- a hidden test suite that **fails before the fix and passes after** (F2P), plus tests that
  must **keep passing** (P2P).

The agent reads the bug write-up, investigates via the tools, fixes the code, and is graded
by re-running the upstream PR's own tests.

## How we convert it

We keep the *task* and swap the *plumbing*. Concretely:

1. **Repo** — fetched from the public APEX-SWE dataset at build time (APEX ships no base
   commit, so we pull its vendored snapshot) and built in the agent image.
2. **Incident data** — a small "seed" step downloads APEX's `data/` and runs our converter
   (`tools/apex_to_clones.py`), which rewrites it into the three clones' seed formats:
   - Plane issues  → **ticketvector** `state.json`
   - Mattermost/Matrix chat → **slack-service** `scraped.json`
   - Loki `*.log`  → **gauge** `state.json`
3. **Grading** — the upstream `golden.patch` (oracle), `test.patch` (hidden tests), and the
   F2P/P2P test IDs are copied over unchanged; the verifier runs the repo's own test command.
4. **Prompt** — APEX's task instruction is reproduced, with its "Available Tools" section
   rewritten to point at the clone CLIs (`gcx`, `linear`/`jira`, `slack`) instead of raw
   Loki/`mcp-loki`.

## What is KEPT the same (or essentially the same)

- **The repo + the bug**: same upstream source snapshot, same buggy code.
- **The grading**: `golden.patch`, `test.patch`, and the exact F2P/P2P test IDs are byte-for-byte
  the upstream PR's. Reward is the repo's own test result — independent of the clones.
- **The task prompt**: the detailed multi-issue bug write-up is reproduced verbatim.
- **The incident *content***: the issues, chat messages, and log lines are preserved — same
  facts, same distractors. Only the container/format changes, not what the agent can learn.
- **The multi-surface premise**: the agent still has a tracker + chat + logs to investigate,
  and in practice does (trials show `linear`/`slack`/`gcx` all used).

## What CHANGES (kept, but not identical)

- **The services** become lighter clones: Plane→ticketvector, Mattermost→slack-service,
  Loki+Grafana→gauge. The agent reaches them through CLIs/MCP (`linear`, `slack`, `gcx`,
  `mcp-grafana`) instead of raw HTTP/Plane/Mattermost APIs.
- **The data formats** are adapted: Matrix chat events → flat `{channel,author,content,ts}`;
  full GitHub issue dumps → ticketvector issues (a *searchable* tracker, not "assigned to me");
  raw Django/geth log lines → gauge log entries with parsed `{service,level}` labels. Content
  is preserved; the on-disk shape differs.
- **Sourcing**: APEX vendors everything into the task; we fetch repo + data from the dataset at
  build time to keep our git light.

## What is LOST

- **Exact service fidelity**: gauge is a Grafana/Loki *stand-in* with a simple query engine
  (label match + `|=` substring), not real LogQL/PromQL or a Grafana UI; ticketvector and
  slack-service cover the common subset of Plane/Mattermost, not every endpoint. Tasks that
  depended on an exotic Loki query or a Plane-specific feature could behave differently.
- **APEX's secondary files**: `prompt_statement.md` (short user-voice restatement),
  `requirements.json`, and `interface.md` are not wired in (the detailed instruction carries
  the spec). Matrix room metadata (multiple rooms, membership events) is flattened to channels.
- **Tool-use enforcement**: APEX *instructs* "you MUST use observability tools" but, like
  APEX, grading does not check it — tool use is captured in the trajectory but not rewarded.

## What is GAINED

- **Lighter + cheaper**: three published images instead of six (Plane+Postgres+Redis+Loki+
  Grafana+Mattermost), lower RAM/disk, faster startup, fully deterministic offline seeds.
- **A reusable converter**: any APEX Observability task → clone seeds with one command.
- **Clone-independent grading**: the verifier only depends on the repo's own tests, so the
  diagnostic surface and the scoring are cleanly separated.
- **Agent-native tools**: `linear`/`slack`/`gcx` CLIs + MCP servers, the same surface used
  across our other clone tasks.

## Net

The agent solves the **same bug** with the **same grading** and the **same investigable
facts** — on a lighter, deterministic substrate. The trade is service-API exactness (real
Loki/Grafana/Plane/Mattermost) for portability, cost, and determinism.
