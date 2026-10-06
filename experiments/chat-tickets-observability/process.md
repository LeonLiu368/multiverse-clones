# chat-tickets-observability — design report

## What these tasks measure

Two **observability / incident-triage** agent-eval tasks. The agent is on-call for a real
OSS service checked out at its **pre-fix base commit** in `/app/repo`, and must fix an active
production bug. The failing regression test is **hidden**, so the agent cannot learn *which*
bug to fix from the repo alone — it must recover that from two seeded surfaces it operates
**only through tools**:

- **ticketvector** (`ghcr.io/abundant-ai/ticketvector-service`) — a Jira/Linear-style issue
  tracker, served as a sidecar on `:8765`. The agent reads the incident ticket + a realistic
  backlog of distractors via the `linear` / `jira` CLIs (remote backend, agent mode).
- **slack** (`ghcr.io/abundant-ai/slack-service`) — a Mattermost-backed Slack Web API, served
  as a sidecar on `:80`. The agent reads the on-call thread via the `slack` CLI / `slack-mcp`.

**Both surfaces are load-bearing.** The ticket carries the symptom and tells the agent which
of many open issues is the live incident, and points at the on-call channel; the chat thread
carries the exact code path and the *agreed* fix — reached only after several wrong theories
(red herrings). The agent must read and disambiguate, not grep one keyword: `linear issue
search` and `slack search` both return misleading hits on purpose.

The reward is computed by re-running the PR's **own regression test** against the candidate
repo (deterministic fail→pass). `nop`=0 (no edit → test still fails), `oracle`=1 (apply
`golden.patch` → test passes).

## Tasks

Both reuse already-validated paperless-ngx PRs (Python/pytest, light build; the base commit,
`golden.patch`, `test.patch`, and `test_metadata.json` are carried over from the
`apex-swe-variants` group). Only the observability layer differs — tickets + chat here vs.
plane/mattermost/loki there — making this a clean A/B on the discovery surface.

| Task | PR | Incident | Hidden F2P test |
|---|---|---|---|
| `variant-paperless-ngx-12865-chat-tickets` | [#12865](https://github.com/paperless-ngx/paperless-ngx/pull/12865) | `WriteBatch.__exit__` releases the Tantivy index writer only on the success path → a batch that errors mid-commit leaks the writer + its lock → next batch `LockBusy` → indexing stalls. Fix: dispose the writer in a `finally`. | `test_backend.py::TestWriteBatch::test_writer_released_when_commit_fails` |
| `variant-paperless-ngx-12856-chat-tickets` | [#12856](https://github.com/paperless-ngx/paperless-ngx/pull/12856) | Index-lock retry has no backoff → lock contention / retry storm. | `search/test_lock_backoff.py` |

## Architecture (per task)

3-container compose: `main` (agent + repo + both client CLIs) + `slack` sidecar + `ticketvector`
sidecar. Services reach each other by compose service name; no `networks:`/`ports:` (Harbor
injects `network_mode`); `platform: linux/amd64`. Seed data is mounted **only into the
sidecars**, never into `main`, so the agent cannot read it off disk — only through the tools.

- **No vendored client source.** Both toolsets are baked into their published images and pulled
  into `main` via `COPY --from` (pinned by digest, same digest the sidecar runs):
  `slack`/`slack-mcp` + `/opt/slackcli` from slack-service; `linear`/`jira`/`world-issues` +
  `/opt/ticketvector` from ticketvector-service (zero deps; remote mode is stdlib-only).
- **slack** self-seeds from the mounted `data/slack/scraped.json` (the image's baked entrypoint
  boots Postgres+Mattermost, runs `seed.py`, then serves the gateway on `:80`).
- **ticketvector** is seeded by authoring `data/ticketvector/state.json` directly in the
  `FakePlaneBackend` snapshot schema (the `world-issues seed reset` CLI is hardcoded to a
  built-in payments fixture and cannot load a custom world). The fixture is mounted read-only at
  `/seed/state.json` and copied to the server's writable state path at boot.

Seed fixtures are produced by committed, deterministic generators (`data/*/generate.py`); both
the generators and their outputs (`scraped.json`, `state.json`) are committed.

## Verifier / anti-reward-hacking

Split harness (`tests/test.sh` orchestrates → `run_verifier.sh` owns reward). `stage_data.sh`
reverts the test file the hidden patch touches so the agent cannot weaken the verifier; the
hidden `test.patch` is applied at verification time and never present in the agent image;
`solution/` is hidden from the agent. The reward is recomputed from the real test, not a proxy.

## Validation

Per task: `docker compose up --build`, wait for all three healthy, confirm `slack channels` and
`linear issue list` return seeded data inside `main`, then `nop → reward 0` and
`solve.sh → reward 1`. Then validate the manifest and dry-run `oracle`+`nop` via Oddish before
any model trial.
