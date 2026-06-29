# Phase 1 — Stand up & run: agent + gateway, Harbor-style (R1, R2 runtime gates)

Goal: prove the clone cold-boots as a **two-container agent + gateway** task, that the **`:prod-v1`
gateway serves its baked DB with no mount** (GHCR image DB seeding), and that the bundled verifier
scores **nop=0 / oracle=1**. Everything here is run, not read.

> **The two containers.** **agent** (`main`) = built from `environment/Dockerfile`, neutral base,
> data-free, under test. **gateway** = the service sidecar (the clone's API + CLI/MCP + seeder),
> pulled from GHCR (or `build:`+`image:`). The agent reaches the gateway only over HTTP by name.

## 1. Inventory the gateway image trio + agent
Find which exist and where:
- `<svc>-service` base gateway image (API + CLI/MCP tools, **no data**)
- `<svc>-service:prod-v1` (**corpus DB baked into the image**) and `:empty` (mount target)
- the **agent** Dockerfile (`environment/Dockerfile`, neutral base) — built by Harbor, not pulled
- the task `environment/docker-compose.yaml` (or `examples/.../docker-compose.yaml`)

A missing `:prod-v1`/`:empty` pair is **R2.b**; a `:prod-v1` that doesn't bake the DB is **R2.j**;
baking task data into a per-task gateway image (instead of mount) is **R2.d**; an agent built
`FROM <svc>-service` (backend artifacts leak into the agent) trends toward an **R2.k/c** finding.

## 2. Cold boot (no registry creds needed — R1.5)
From a clean state (no leftover volumes/containers), with only documented env vars:
```bash
docker compose -f <compose> up --build -d        # builds `main` + any build:+image: gateway, then up
```
Assert, **observing actual behavior**:
- the gateway reaches **healthy** (its `depends_on.condition: service_healthy` healthcheck fires) — R1.1
- the gateway resolved **without an `unauthorized` pull**: either its GHCR package is public, or the
  service has `build:`+`image:` so `compose build` tagged it locally — R1.5
- the **agent** resolves + reaches the gateway **by name over HTTP** (`curl http://<svc>:<port>/health`
  from inside `main`) — R1.2
- nothing required hand-editing a file to boot — R1.2

Record the exact command sequence and trimmed boot log for Reproduction.

## 2b. GHCR image DB seeding — the `:prod-v1` baked-DB probe (R2.j)
The headline seeding check. Boot the **`:prod-v1`** gateway tag **with no fixture mount** and confirm
it serves the full baked corpus:
```bash
# point the gateway service at the prod-v1 tag, remove any fixture volume, then:
docker compose -f <compose> up -d <gateway>
docker compose exec main sh -c "curl -fsS http://<svc>:<port>/<a-seeded-read>"   # returns corpus data
```
- ✅ pass: `:prod-v1` answers seeded reads out of the box; the per-task mount is **ignored** (the baked
  DB already exists). Switching `:empty ↔ :prod-v1` is the **image tag alone**.
- ❌ fail (R2.j): `:prod-v1` is empty without a mount, or the DB isn't baked (`COPY <corpus>.db → $…_DB`
  missing from `Dockerfile.prod-v1`), or it requires a runtime seed step.
Then sanity-check the **other** path: `:empty` + a fixture mount also boots and serves the mounted data.

## 2c. Image hygiene (R2.k)
- **Multi-arch:** `docker buildx imagetools inspect ghcr.io/<org>/<svc>-service:prod-v1` lists
  `linux/amd64` **and** `linux/arm64` (amd64-only breaks `FROM <svc>-service` agent builds on arm dev
  machines).
- **Leak:** `docker run --rm <agent-image> grep -rs '<task-answer>' /opt /app /usr/local` finds
  nothing — the answer isn't reproducible from the baked gateway source shipped in the agent.

## 3. nop / oracle (the load-bearing gate — R1.3)
The verifier entrypoint is `tests/test.sh`, which must write `/logs/verifier/reward.txt`.
- **nop:** run with an empty/absent solution → expect `0.0`. A nonzero nop means the task is passable
  without doing the work (reward-hackable) — **fail R1**.
- **oracle:** run `solution/solve.sh` then the verifier → expect `1.0`. An oracle <1 means the
  intended solution doesn't satisfy the verifier — **fail R1**, the clone/task is internally broken.
- A cloud `HARNESS_ERROR — Classification Failed` row on a nop/oracle baseline is the
  trajectory-classifier choking on a no-trajectory run, **not** a task failure — read the QA verdict,
  not the row color.

## 4. Runtime isolation & canon recon (R2.c/d/f/g)
- **No seed on disk in the agent:** `docker compose exec main sh -c '[ ! -e <state-path> ] && echo SEALED || echo LEAK'`. A LEAK is **R2.g/c fail** — the agent could read the answer key.
- **State only over HTTP:** the agent's tools point at `http://<svc>:<port>`; there's no mounted DB in `main`.
- **Per-task data by mount into the gateway:** confirm task data is bind-mounted into the **gateway**
  and applied to a runtime copy at boot — not `COPY`d into a per-task gateway image (R2.d).
- **No `networks:` block** in the compose unless the clone documents an isolation exception (e.g.
  pinned-subnet IP isolation, as gh-clone uses). Undocumented `networks:` is a known runtime-failure
  cause and an **R1.4/R2.f** finding.

## 5. Determinism spot check (R1.5, advisory)
Rebuild the seed from the same input twice; ids/names should be byte-identical (importers use a
deterministic name→id hash). Divergence undermines the verifier and is worth an action item.

## Automate it
`assets/audit_harness.sh <compose-file> <service-name> <health-url>` does standup → wait-for-healthy →
health probe → isolation check → teardown, and prints a pass/fail line per check. Use it as the
scaffold; extend the probes per clone.

## What to carry into the report
- R1 result + evidence (`nop=…, oracle=…`, boot command, health output, creds-free pull/build).
- Runtime canon gates: c, d, f, g **and the seeding gates j (prod-v1 baked-DB boots mount-free) + k
  (multi-arch, no leak)** as ✅/⚠️/❌ with the command that showed each.
