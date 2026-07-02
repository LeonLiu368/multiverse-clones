# Clone audit — discord-clone (self-audit)

**Verdict: MEETS Clone Standard v1** (6/6 gating requirements pass, no P0 action items).

- **Clone:** discord-clone — Discord REST API v10, authored-in-tree (no upstream OSS).
- **Fidelity:** T2 (declared = observed) — handwritten SQLite gateway + a real
  `messages/search` param grammar and snowflake message-history pagination.
- **Audited:** 2026-07-02, via the local venv + a local docker build of the image
  trio + thin agent (GHCR publish not exercised — see the multi-arch note below).

## What it handles well

- **Two-container agent+gateway, Harbor-style (R1).** `main` (thin agent) + the
  `discord` gateway (`discord-service:prod-v1`) wired by healthcheck + `depends_on`,
  no `networks:` block. Verified end-to-end in the real two-container docker shape:
  **nop = 0.0, oracle = 1.0**, and again locally via the `REWARD_DIR` path.
- **GHCR image DB seeding (R2.j).** `:prod-v1` bakes `discord_corpus.db` and serves
  the full "Acme Engineering" guild **mount-free** (verified: `/users/@me/guilds`,
  `messages/search?content=PRICING_CACHE_TTL` → 2 hits, pins). `:empty` boots
  data-free (`[]` guilds); switching is the image tag alone.
- **Leak rule (R2.k).** The agent is a neutral `python:3.12-slim` with `api/` + `seed/`
  stripped: `import discordclone.seed` / `import discordclone.api` raise
  ModuleNotFoundError; a grep of the agent image for `PRICING_CACHE_TTL` / `INC-4471`
  / any discord `*.db` finds nothing — the answer is neither greppable nor recomputable.
- **CLI + MCP in parity (R3).** 15 agent capabilities, each one CLI command **and**
  one MCP tool over the shared `DiscordClient`; 14 parity assertions green.
- **Real envelopes (R4).** Snowflake string ids, ISO-8601 timestamps,
  `before/after/around&limit` newest-first history, the `{total_results,messages:[[msg]]}`
  search shape, and Discord error codes (401, 10003/10008/10004/10013/10007, 50035/50006).
- **6 assessment-grade capabilities (R5).** search-grammar (5/5), history pagination,
  send write→read round-trip (hydrated `id`/`timestamp`/`author`/`type`/`reactions`),
  reaction round-trip, member pagination, resolution chain. The bundled
  `discord-incident-triage` task exercises search→fix-code→post→read-back.
- **Unit tests (R6).** 75 pass — every endpoint (happy + error), every CLI command,
  every MCP tool, parity, and an isolation suite that runs against the built agent image.

## Notes / non-blocking

- **Multi-arch is CI-declared, locally unverified.** `.github/workflows/discord-service-image.yml`
  builds all four images (`base`, `:empty`, `:prod-v1`, `discord-agent`) for
  `linux/amd64,linux/arm64` with the built-in `GITHUB_TOKEN`. Local builds are
  single-arch; per the standard this scores the multi-arch half of R2.k as
  verified-at-publish, not a local failure (the `build:`+`image:` dual / pull-free
  path keeps R1.5 satisfied).
- **Docker required** for the isolation suite (R6.3) and the two-container nop/oracle
  run; both were executed locally for this audit.

## Action items from the independent audit — all closed (2026-07-02)

The independent auditor returned `meets_standard = true`, 0 P0, with 5 non-gating
action items. All five are now resolved in the tree:

1. **P1 (R1 portability).** The task compose was pull-only against an unpublished
   GHCR package. Fixed: the `discord` gateway now carries a **`build:`+`image:` dual**
   (`docker/Dockerfile.prod-v1.standalone`, a self-contained one-pass prod-v1 build
   with the corpus baked in). `docker compose build` builds and tags
   `ghcr.io/abundant-ai/discord-service:prod-v1` locally with **no GHCR pull and no
   creds** (R1.5). Re-verified in the two-container shape: **nop=0.0, oracle=1.0**.
2. **P1 (R2 arch pin).** Dropped the hard `platform: linux/amd64` pins from the task
   compose so it builds/runs native on the host arch. Re-verified on **arm64**
   (host + built gateway image both arm64, no emulation).
3. **P2 (R5 count).** The `Get member` endpoint row now carries the **★** marker, so
   the matrix has **6 marked rows** matching `assessment_grade_count: 6`. COVERAGE
   item 6 references that endpoint instead of prose.
4. **P2 (R7 MANIFEST).** The `discord-clone` entry in `clones/MANIFEST.json` is the
   provenance object `{strategy:"authored-in-tree", repo:null, commit:null,
   spec:"clone-spec.yaml", …}` (not a bare string).
5. **P2 (R4 search parity).** `messages/search` now adds `"hit": true` to each matched
   message object (`store.search_messages`), with a test asserting it.

**Remaining (infrastructure, not a repo change):** the auditor's other P1 (R2) —
*publish the image trio multi-arch to a PUBLIC GHCR package* — cannot be done from the
build environment (no registry creds; nothing committed). CI
(`.github/workflows/discord-service-image.yml`) already declares the multi-arch
publish; it takes effect on push-to-main. Until then the `build:`+`image:` dual keeps
the task pull-free (R1.5), so this is verified-at-publish, not a local blocker.

Re-verification after the fixes: **80 unit tests pass** (+ isolation suite green
against the built agent image), and the new compose cold-boots to **nop=0/oracle=1**.
