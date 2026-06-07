# How the environment works (start to end)

Plain-English walkthrough of the isolated 2-container artifact: where the data comes from, how
the containers talk, how the simulation is hidden, and how the verifier scores. Canonical
reference: [`selfcontained/isolated/`](../selfcontained/isolated/).

## The two containers (from ONE pushed image + a thin agent)
- **`api` (sidecar)** — the backend. The prebuilt **`slack-service`** image (pulled, not built):
  **real Mattermost** bound to `127.0.0.1:8065` (never exposed) + the **Slack Web API gateway**
  (`slackgw`, FastAPI) on `:80`. The agent reaches only the gateway, at the neutral host `api`.
- **`main`** — where the **agent** runs. A thin `python:slim` build (no Mattermost tells): `curl` +
  the official **`slack_sdk`**, `python` + `pytest`, and the **codebase at `/workspace`**. Slack
  creds are baked as image env (`SLACK_API_URL=http://api`, `SLACK_BOT_TOKEN=xoxb-…`).

There is **no `networks:` block** — Harbor injects `network_mode` on the agent service, which is
mutually exclusive with `networks:` (a real Modal failure). Isolation comes from binding
Mattermost to localhost inside `api`, not from network plumbing. Service-name DNS still resolves
`api`. Both services pin `platform: linux/amd64`.

## Step by step
1. **Pull the backend, build the thin agent.** The backend is one prebuilt image,
   `ghcr.io/abundant-ai/slack-service` (Mattermost + gateway + seeder), pushed by CI and **pulled**
   by the task's `api` service — never rebuilt. The task's `environment/` carries only: the thin
   agent `Dockerfile` (+ `main-entrypoint.sh`) that Harbor builds for `main`, the `docker-compose.yaml`,
   the heavy chat (`data/mattermost/scraped.json`, mounted into `api`), and the `codebase/` (COPY'd
   into the agent). See [IMAGE-RELEASE.md](IMAGE-RELEASE.md).
2. **The `api` sidecar boots and seeds itself.** `api-entrypoint.sh` starts Postgres, launches
   Mattermost on `127.0.0.1:8065`, waits for it, then runs `seed.py`, which builds the workspace
   from `data/mattermost/scraped.json` — admin, team `test-demo`, channels, users, message
   history. **Channels/users via REST, posts via SQL** (to preserve timestamps); raw-SQL entities
   don't behave under app operations. The seed is **heavy and noisy on purpose** (~500 messages,
   ~7 channels, deterministic via `generate.py`) — the one fact the agent needs is buried among
   distractors and *superseded* values.
3. **The gateway comes up.** Once seeded, `api-entrypoint.sh` execs the Slack gateway on `:80`.
   The compose healthcheck (`/api/auth.test` up + MM ping) only passes after this — so "api
   healthy" means "seeded and serving."
4. **The agent starts.** `main` `depends_on: api healthy`, so it starts post-seed. Its baked env
   makes curl + `slack_sdk` work immediately against `http://api`.
5. **The agent acts.** It reads `instruction.md` (symptom + "you have the Slack Web API"), uses
   `slack_sdk`/curl to recover the buried fact from the chat, edits the code at `/workspace`, and
   — for the incident task — posts a postmortem via `chat.postMessage`.
6. **The verifier scores.** `tests/test.sh` → `tests/run_verifier.sh` (in `main`). It copies the
   candidate package **plus the trusted tests** (canonical invariant tests + a HIDDEN
   `test_grade_*.py` that pins the answer) into a fresh **verifier-owned** `/tmp` dir and runs
   `pytest` there — so the visible `/workspace/tests` are never trusted, and the answer can't be
   read from them. Communication checks (e.g. the postmortem) are read back **through the gateway**
   (`conversations.history`), since Mattermost isn't reachable. Result → `/logs/verifier/reward.txt`.
7. **Bracketed.** `nop` (do nothing) → 0; `oracle` (`solution/solve.sh`) → 1. Each task is also
   checked so a wrong-but-invariant fix scores 0, and the incident task scores 0 if the code is
   fixed but the postmortem isn't posted.

## Why the agent can't tell it's a simulation (recon hardening)
From `main`: Mattermost `:8065` is **refused**, `/api/v4` and stray paths return Slack-shaped
`unknown_method`, server/version headers are **scrubbed**, and the only host is the neutral `api`.
The chat is reached exactly like a self-hosted Slack-compatible endpoint.

## Why it's a good benchmark
- The fix-critical fact lives only in the chat → the agent **must** use the tool.
- Heavy, noisy, deterministic seed → non-trivial retrieval, reproducible runs.
- Hidden grader + invariant-only visible tests + isolated grading dir → no shortcut, no tampering.
- `nop=0 / oracle=1` (+ wrong-impl=0) bracket on every task.
- Action beyond coding (the incident postmortem) → measures tool use that isn't just editing files.
- Self-contained, no `networks:`, amd64 → runs the same locally and on Modal.
