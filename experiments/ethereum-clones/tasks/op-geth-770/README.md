# variant-ethereum-optimism-op-geth-770-observability

APEX-SWE-style multi-service DevOps observability task, Harbor format, **ticketvector** architecture.

- **Source PR:** https://github.com/containers/podman-compose/pull/1271
- **Repo:** `containers/podman-compose`
- **Base SHA:** `528b5d2d7cc087ede3e07d2d442b881880da711e`  ·  **Merge SHA:** `71e0fbd392dc5df2506013c5f851657ca139e267`
- **Category:** container-tooling / argument-generation regression

## Incident

The agent is the on-call engineer. The active production work item lives in the local
issue tracker, reachable through the `linear` and `jira` CLIs (backed by the
`ticketvector` service). The primary incident is **TV-1271 — podman-compose drops detailed healthcheck timing options**.

> Compose healthcheck blocks with interval/timeout/retries/start_period/start_interval stop emitting the full expected Podman run arguments, so dependent services never promote to ready.

Corroborating observability context (symptom-level, no fix given) is baked at
`/app/observability/` (Loki-style `app.log`, Mattermost thread). Four distractor
tickets (TV-INT-41, TV-OPS-77, TV-QA-18, TV-DOC-12) seed the tracker; touching them fails verification.

## Environment (multi-service)

- `main` — agent container; target repo checked out at `/app/repo` (pre-fix base commit),
  `linear`/`jira` CLIs on `PATH`.
- `ticketvector` — issue-tracker service (`:8765`) holding mutable ticket state.

## Verification (hidden)

`tests/test.sh` orchestrates the split harness:
1. `stage_data.sh` copies the hidden regression test into the repo
   (`tests/unit/test_ticketvector_healthcheck_flags.py`).
2. `run_candidate.sh` — candidate edits are already in `/app/repo`; no separate artifact.
3. `run_verifier.sh` runs `python -m unittest tests.unit.test_ticketvector_healthcheck_flags`.
4. `check_ticket_state.py` asserts the ticket workflow: **TV-1271** moved to *In Review*
   through the tracker (history shows In Progress → In Review), assigned to `agent`,
   with an investigation comment, commit-link evidence, and a dry-run PR receipt — and
   that **no distractor ticket was mutated**.

Reward is `1` iff the hidden unit test passes **and** all ticket-state checks pass; else `0`.

Upstream provenance test command:
`python -m unittest tests.unit.test_container_to_args.TestContainerToArgs.test_healthcheck_options`

## Gates

- `nop` → reward `0.0` (base repo fails the hidden test; no ticket workflow performed).
- `oracle` (`solution/solve.sh`) → reward `1.0` (applies `solution/golden.patch`, then drives
  the full ticket workflow via `linear`/`jira`).

## Data provenance

- **Real OSS data:** source repo snapshot at base commit, product fix (`solution/golden.patch`),
  hidden regression test.
- **Generated:** ticketvector ticket state, Loki/Mattermost observability context.

## Local validation

SWE correctness core validated locally in a minimal container: the hidden unit test
**fails on the base repo** and **passes after `solution/golden.patch`**. Full multi-service
`nop`/`oracle` gates run on the Oddish/Daytona backend via the experiments CI.
