# Boundary decision (R2 structural) — what this repo's clone surface IS

The `jira`/`linear` CLI, the issue HTTP API (`POST /rpc` on `:8765`), the JQL engine, and the
synthetic seed generator all live in the **external** `ghcr.io/abundant-ai/ticketvector-service`
image. **This repo** owns: the converters (`tools/*.py`), the image-trio Dockerfiles
(`selfcontained/base/`), the read-only Linear GraphQL gateway (`linear/`), the tasks, and — added
in this pass — **the jira MCP server (`mcp/`)** and the agent-image hardening.

**Decision (explicit):** we treat THIS repo's clone surface as *"the jira/linear tooling layered on
the ticketvector engine."* The ticketvector image is the **gateway engine**; this repo is the
clone's tooling + packaging + tasks around it. Consequences:

- **MCP (R3) lives here** (`mcp/`), as a *thin client* of the same ticketvector `/rpc` API the CLI
  hits — not in the ticketvector repo. It mirrors the CLI 1:1 (parity proven in `tests/test_parity.py`).
- **The agent ships only the thin client surface (R2.k).** `selfcontained/base/Dockerfile.agent`
  no longer `COPY`s `/opt/ticketvector` wholesale; it runs `strip_agent_tooling.py`, which deletes
  the gateway's API + world-builder source (`server/seed/plane/demo/runtime/snapshot.py`) and
  patches `cli.py` so the remaining thin-client CLI still imports. After the strip:
  `import world_issues.seed` raises `ModuleNotFoundError` and no `seed`/`server` source survives.
- **The corpus DB was never in the `world_issues` package** — it lives only in the baked gateway
  DB (`:prod-v1`) or a mounted fixture (`:empty`). So even the (now-removed) generator could only
  regenerate the unrelated demo `PAY` world, never the ENG/WEB task corpus.

## Known blocker that belongs to the ticketvector repo (multi-arch, R2.k)

The base `ghcr.io/abundant-ai/ticketvector-service` is **published linux/amd64-only**. The CI
workflow (`.github/workflows/ci.yml`) declares `platforms: [linux/amd64, linux/arm64]` and pushes
the gateway+agent multi-arch, but the **arm64 leg cannot succeed until the ticketvector base is
republished multi-arch** — a change that must be made in the ticketvector repo, not here. The
arm64 matrix entry is marked `continue-on-error` so it surfaces the blocker without failing the
whole run; amd64 is the supported arch today. Per the standard, the multi-arch half of R2.k scores
`n/a (unverified)` locally and is a publish-time blocker owned upstream.

# Prod corpus + per-task seeding (Jira clone)

This mirrors the Slack clone's `docs/PROD-OVERLAY.md`, adapted to ticketvector. The big difference:
**ticketvector loads a single `state.json`; there is no boot-time overlay-merge** like the Slack
gateway's `/data/slack-overlay`. So per-task seeding is "pick which state.json the service serves",
not "merge an overlay onto prod at boot".

## The shared images

- `jira-gateway:prod-v1` — `ticketvector-service:latest` + the ENG corpus baked at
  `/var/lib/ticketvector/state.json` (`selfcontained/base/Dockerfile.gateway`).
- `jira-gateway:empty` — `ticketvector-service:latest` with the stock demo state **removed**
  (`selfcontained/base/Dockerfile.empty`). Serves nothing until a task mounts a `state.json`.

Both are PULLED as a task's `jira` sidecar; the agent never gets them.

## The three seeding paths

### 1. Prod corpus, baked (no mount) — `jira-status-lookup`

Use `jira-gateway:prod-v1` as-is. The service serves the full ENG corpus. The task mounts no data.
Best for read/observability tasks over the real corpus.

```yaml
jira:
  image: jira-gateway:prod-v1
```

### 2. Custom project, mounted on empty — `jira-assignee-count`

Use `jira-gateway:empty` and mount a full per-task `state.json` read-only. The service serves exactly
that project. Best for clean, deterministic, low-cardinality tasks (keep total issues < 50 to avoid
the CLI's default 50-item page, or paginate via `next_cursor`).

```yaml
jira:
  image: jira-gateway:empty
  volumes:
    - ./data/state.json:/var/lib/ticketvector/state.json:ro
```

The `state.json` shape is exactly what `tools/jira_to_state.py` emits (project / users / states /
labels / issues / comments). You can hand-author a small one (see
`tasks/jira-assignee-count/environment/data/state.json`) or convert a real export.

### 3. Prod-with-planted-issues, baked per dataset (when you need both)

If a task needs the heavy ENG corpus *and* its own planted issues (the closest analogue to the Slack
overlay), bake a merged state into a new gateway tag:

```dockerfile
FROM --platform=linux/amd64 ghcr.io/abundant-ai/ticketvector-service:latest
COPY data/eng-plus-planted-state.json /var/lib/ticketvector/state.json
```

Produce `eng-plus-planted-state.json` by loading the prod state and appending your planted issues to
`issues[]` (and any comments to `comments{}`), then tag it `jira-gateway:<dataset>`. This is more work
than a mount, so prefer path 1 or 2 unless a task genuinely needs prod-scale context + custom rows.

## Isolation invariant

In all three paths the data lives **only in the sidecar**. The agent's `main` container is built FROM
`jira-agent:latest` and has no `state.json`; it reaches issues only via the `jira`/`linear` CLI in
`WORLD_ISSUES_BACKEND=remote` mode (`PLANE_BASE_URL=http://jira:8765`), with
`WORLD_ISSUES_AGENT_MODE=1` blocking admin/seed/runtime subcommands.
