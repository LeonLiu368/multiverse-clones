# APEX-SWE-clones — two demo samples (Jun 22)

Two **exact mercor/APEX-SWE Observability tasks** re-platformed onto our service-clone stack. These
are the quality bar we want for Task Farm: a **real OSS app, a real bug, a real problem**, with the
incident evidence served through realistic tools and grading done by the project's **own test suite** —
not hand-authored fixtures.

## Why these clear the bar (vs. the episode-built tasks)

| Axis | Episode-built taskfarm | These (APEX-clones) |
|---|---|---|
| App | thin clone (e.g. Sentry stub) | **real upstream app** (paperless-ngx / podman-compose) |
| Bug | synthesized | **the actual upstream bug** the PR fixed |
| Verifier | hand-written, sometimes brittle/ambiguous | **the upstream PR's own pytest** (F2P/P2P) — robust, unambiguous |
| Logs | proof-of-concept | **real application request logs** (200/400/500 + info noise) |
| Leakage | — | audited clean (no PR diff / ticket link on agent-visible surfaces) |

The agent investigates a realistic incident across three clone tools — **gauge** (Grafana/Loki logs),
**ticketvector** (Jira/Linear issue tracker), **slack** (team chat) — then fixes the root cause in
`/app/repo`. Data is sealed behind the tools (agent can't read it off disk).

## Sample 1 — `podman-compose-2-1238` (Go/Python; x-podman network-name compat) ✅ validated
- **Bug:** env-var vs compose-file precedence for `x-podman.default_net_name_compat`, breaking service
  discovery (`microservicea_default` vs `microservice-a_default`).
- **Buried signal (gauge logs):** `error … expected network name: microservicea_default (compat)` /
  `actual: microservice-a_default (native)` / `service discovery failed`.
- **Fix:** `podman_compose.py` net-name logic. **Grader:** upstream pytest (3 F2P + 40 P2P).
- **Results (run 8755a5d4):** nop = GOOD_FAILURE, oracle = GOOD_SUCCESS, **gemini-3.1-pro solved it on
  both trials** (Legitimate Solution ×2). Baseline holds and a frontier model can solve it.

## Sample 2 — `paperless-ngx-10555` (Python/Django; secure webhook delivery)
- **Bug:** webhook delivery lacks SSRF / redirect / host-header hardening.
- **Spec + signal:** issue acceptance criteria (block private/loopback IPs, no auto-redirects, strip
  user Host header, 5s timeout) + Django request logs in gauge.
- **Fix:** `documents/signals/handlers.py` + `settings.py`. **Grader:** upstream pytest (5 F2P + 52 P2P).
- **Results:** baseline + model trials completing in the current run (heavy Django image).

## Models
Re-running with the **priority models — codex (gpt-5.2-codex) ×2 and claude-code (opus-4-7) ×2** — plus
gemini ×2 and the nop/oracle baseline (16 trials). Live: PR #509 → experiment on oddish.app.

## How they were made (repeatable)
`apex_to_clones.py` converts each APEX task's `data/{plane,mattermost,loki}` → ticketvector + slack +
gauge seeds at standup; the upstream repo + PR-derived tests are fetched from the public dataset. The
recipe is captured in the `clone-task-builder` skill. The remaining ~24 APEX Observability tasks
convert the same way — this is the production path to replace episode-built tasks.
