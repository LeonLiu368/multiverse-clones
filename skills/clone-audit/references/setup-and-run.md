# Phase 1 — Stand up & run, Harbor-style (R1, R2 runtime gates)

Goal: prove the clone cold-boots into the **two-container Harbor shape** and that the bundled verifier
scores **nop=0 / oracle=1**. Everything here is run, not read.

## 1. Inventory the build surface
Find, per the canon, which of these exist and where:
- `<svc>-service` base image (engine + tools, no data)
- `<svc>-gateway:prod-v1` (corpus baked) and `:empty` (mount target)
- `<svc>-agent` (thin, data-free)
- the task `environment/docker-compose.yaml` (or `examples/.../docker-compose.yaml`)

If images aren't published, note the local build path (`build.sh`, `Dockerfile.service`, etc.). A
missing `:prod-v1`/`:empty` pair is an **R2.b** finding; building the agent per-task instead of
`FROM <svc>-agent` is **R2.d** (gh-clone's known gap).

## 2. Cold boot
From a clean state (no leftover volumes/containers), with only documented env vars:
```bash
docker compose -f <compose> up --build -d        # or the clone's documented standup
```
Then assert, **observing actual behavior**:
- service reaches **healthy** (the `depends_on.condition: service_healthy` healthcheck fires) — R1.1
- the agent container resolves + reaches the service **by name over HTTP** (`curl http://<svc>/health`
  from inside `main`) — R1.2
- nothing required hand-editing a file to boot — R1.2

Record the exact command sequence and trimmed boot log for the report's Reproduction section.

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
- **No seed on disk in the agent image:** `docker compose exec main sh -c '[ ! -e <state-path> ] && echo SEALED || echo LEAK'`. A LEAK is **R2.g/c fail** — the agent could read the answer key.
- **State only over HTTP:** the agent's tools point at `http://<svc>:<port>`; there's no mounted DB in `main`.
- **Per-task data by mount:** confirm task data is bind-mounted into the **sidecar** and applied to a
  runtime copy at boot — not `COPY`d into a per-task image (R2.d).
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
- R1 result + evidence (`nop=…, oracle=…`, boot command, health output).
- Runtime canon gates: c, d, f, g as ✅/⚠️/❌ with the command that showed it.
