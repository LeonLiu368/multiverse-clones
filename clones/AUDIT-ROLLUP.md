# Fleet audit roll-up — Clone Standard v1

Per-clone audits + a creator→auditor fix loop run via the `clone-audit` / `clone-creation` skills
(2026-06-29). Each clone has its own `clones/<name>/audit/{audit-report.md,audit-verdict.json}` with
full evidence. `meets_standard` = every **gating** requirement passes, independently re-verified
(every PASS cites a command the auditor ran).

## Current state: **10 / 10 meet the standard** ✅

| Clone | Verdict | R1 | R2 | R3 | R4 | R5 | R6 |
|---|---|---|---|---|---|---|---|
| notion-clone | ✅ 7/7 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| figma-clone | ✅ 6/6 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| google-workspace-clone | ✅ 6/6 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| gh-cli-clone | ✅ 6/6 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| sentry-clone | ✅ 6/6 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| grafana-clone | ✅ 6/6 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| abundant-logfire-clone | ✅ 6/6 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| abundant-slack-clone | ✅ 6/6 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| aws-clone | ✅ 6/6 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| abundant-jira-clone | ✅ 7/7 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

(jira's gating_total is 7 — it carries the operator-boundary sub-gate explicitly.)

## What the fix loop did (the recurring work)
Round 1 found 9/10 failing on the same systemic gaps; one `clone-creation` pass + independent
re-audit closed them:

- **R2 GHCR baked-DB canon (was the #1 fleet gap):** built the `:prod-v1`+`:empty` image trio for
  every clone — `:prod-v1` bakes the corpus and boots **mount-free**, verified live. gh-cli's
  Forgejo-backed `:prod-v1` bakes a seeded Forgejo data dir (the "OSS won't bake" worry didn't hold);
  slack/jira re-pointed tasks to the existing clean trio + mount model (dropping per-task `COPY` data).
- **R2.k leak (endemic):** stripped the gateway's `api/`+`seed/` source from every agent image — the
  recomputable-generator leak class fixed in notion. Verified by `import <pkg>.seed` raising + no
  source dir, in addition to the literal grep.
- **R3 MCP:** added MCP servers to **aws-clone** (26 tools) and **abundant-jira-clone** (11 tools),
  both thin clients in CLI parity — closing the two CLI-only gaps.
- **R5 write path:** added an agent-facing write + a write→read round-trip task to read-only
  **google-workspace-clone**.
- **R4/R6:** added `docs/COVERAGE.md` matrices and full unit suites (every endpoint/CLI/MCP + CLI↔MCP
  parity + isolation/import-leak) across the fleet.
- Bugs fixed in passing: gh's stale "41/41" coverage counter; aws's log-window ingestion drop; stale
  READMEs (gws/jira/slack); deleted slack's dead root Mattermost gateway.

## Known non-gating follow-ups (do not block `meets_standard`)
- **Multi-arch is a CI *declaration* everywhere.** Each clone's CI workflow declares
  `platforms: linux/amd64,linux/arm64`, but the GHCR packages aren't published/pullable from here, so
  the multi-arch half of R2.k is scored `n/a (unverified)` locally — it becomes a true gate at publish
  time when CI runs on push-to-main. **abundant-jira-clone has a real upstream blocker:** its
  `ticketvector-service` base is published amd64-only, so arm64 can't be produced until ticketvector
  republishes multi-arch.
- A few P2s noted in individual reports (docker-compose test races in aws/grafana-clone that self-skip; stale
  secondary docs in slack; help-string byte-faithfulness untested in figma).

## Reproduce
`clones/<name>/audit/audit-report.md` has the per-clone Reproduction commands; verdicts are
machine-readable at `clones/<name>/audit/audit-verdict.json` (schema:
`skills/_shared/audit-verdict.schema.json`).
