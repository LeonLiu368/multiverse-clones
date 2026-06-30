# Fleet audit roll-up — Clone Standard v1

Per-clone audits run via the `clone-audit` skill (2026-06-29). Each clone has its own
`clones/<name>/audit/{audit-report.md,audit-verdict.json}` with full evidence. `meets_standard` =
every **gating** requirement passes.

| Clone | Verdict | R1 run | R2 canon/seed | R3 CLI+MCP | R4 coverage | R5 assess | R6 tests | P0s |
|---|---|---|---|---|---|---|---|---|
| **notion-clone** | ✅ **PASS 7/7** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 0 |
| figma-clone | ❌ 4/6 | ✅ | ⚠️ | ⚠️ | ✅ | ✅ | ⚠️ | 3 |
| gh-cli-clone | ❌ 4/6 | ✅ | ❌ | ✅ | ✅ | ✅ | ❌ | 5 |
| google-workspace-clone | ❌ 4/6 | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | 3 |
| sentry-clone | ❌ 4/6 | ⚠️ | ❌ | ✅ | ⚠️ | ✅ | ✅ | 3 |
| gauge | ❌ 3/6 | ❌ | ❌ | ✅ | ✅ | ✅ | ⚠️ | 3 |
| abundant-logfire-clone | ❌ 2/6 | ❌ | ❌ | ✅ | ❌ | ✅ | ❌ | 3 |
| abundant-jira-clone | ❌ 2/7 | ⚠️ | ❌ | ❌ | ❌ | ⚠️ | ❌ | 5 |
| abundant-slack-clone | ❌ 1/6 | ⚠️ | ❌ | ⚠️ | ❌ | ⚠️ | ❌ | 2 |
| aws-clone | ❌ 1/6 | ❌ | ❌ | ❌ | ⚠️ | ✅ | ⚠️ | 4 |

**1 of 10 meets the standard.** notion-clone (built to the standard via `clone-creation`) is the
reference; the rest predate the standard and fail on a small set of recurring, systemic gaps.

## Systemic gaps (fix once, apply fleet-wide)

1. **R2 — the GHCR baked-DB `:prod-v1` canon is missing almost everywhere (7/9 fail).** Most clones
   never built the `:prod-v1`+`:empty` image trio with a baked corpus + multi-arch publish. Variants:
   gh-clone bakes data *per task* and builds the agent per task (the inverse of the canon); gauge /
   sentry / logfire / aws have no `:prod-v1` at all; slack *has* the clean trio but no task uses it.
   This is the #1 fleet blocker.
2. **R2.k — the agent ships the gateway's `api/`+`seed/` source (endemic leak class).** figma (task
   agent), gauge, sentry, logfire, jira, slack all leave server/seed source importable in the agent —
   the exact class fixed in notion. Strip it in the agent Dockerfile (build from a neutral base or
   `rm -rf` api/seed; assert `import <pkg>.seed` raises).
3. **R6 — no parity/isolation unit tests (6/9 fail).** Most ship store-level pytest but no
   endpoint/CLI/MCP coverage, no CLI↔MCP parity test, no isolation/import-leak test.
4. **R4 — no machine-checkable `docs/COVERAGE.md` (most clones).** Only gh-clone and figma have a
   coverage matrix; the rest have prose docs the loop can't check.
5. **R3 — no MCP server: aws-clone, abundant-jira-clone.** The two confirmed CLI-only clones.
6. **Multi-arch — single-arch publishes across the board** (CI declares no `platforms:`).
7. **R5 — google-workspace-clone is read-only** (all agent endpoints GET); needs ≥1 write→read
   round-trip to discriminate agents.

## Closest to passing (best ROI for a `clone-creation` pass)
**figma-clone, gh-cli-clone, google-workspace-clone, sentry-clone** (all 4/6). Each needs a focused,
mostly-mechanical pass: build the `:prod-v1` trio + strip the agent leak + add parity/isolation tests
(+ a COVERAGE matrix; + one write path for gws).

## Structural questions (not pure mechanics)
- **abundant-jira-clone**: the CLI, API, JQL engine, and seed generator live in the **external
  ticketvector** image — R3/R4/R6 can't be satisfied here without either vendoring the tool surface in
  or declaring *ticketvector* the clone and this repo its per-task seeder. Decide the boundary first.
- **abundant-slack-clone**: the clean `slack-agent`/`slack-gateway:prod-v1` trio already exists and
  passes its checks — the work is re-pointing the shipped Oddish tasks at the 2-container shape.

## Stale docs caught in passing (cheap fixes)
- gws README claims "Drive+Docs slice" but Calendar+Gmail are fully implemented.
- gh-clone's "41/41 passing" coverage claim is stale (counter breaks on faithful URL output → 23/41).
- jira README says ENG-2016 assignee "Felix Martin"; live corpus returns "Priya Fischer".
- slack repo-root `slackgw/app.py` is a dead Mattermost gateway contradicting the README.
