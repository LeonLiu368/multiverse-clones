# Oddish tasks (abundant-figma-clone)

Harbor/Oddish "observability + codebase" tasks built on the Figma clone. Each task
runs a `figma` service (the single `figma-service` image — `build:` + `image:` in the
compose, so the harness builds it locally and needs no registry auth, while the
`ghcr.io/abundant-ai/figma-service` tag stays available to pull) and provides its
design data **per task** by mounting a `fixture.json` into that service container
only — so the seeded spec is reachable solely through the Figma tools
(`figma-cli` + `figma-mcp`), never readable from the agent's container.

## Tasks

- [`figma-spec-recovery/`](tasks/figma-spec-recovery/) — implement a `PricingCard`
  component to match the finalized design. The exact spec is split across the Figma
  file's node tree and its comment thread, with superseded decoys and a stale node
  value that a later comment overrides. The agent must read both to recover the
  truth, update the code, and post a completion comment. Hidden grader pins the
  spec; the comment is read back through the API. `nop=0 / oracle=1`.

## Run

```bash
# 1) build the one pulled service image (or let CI publish it)
docker build -f docker/Dockerfile -t ghcr.io/abundant-ai/figma-service:latest .

# 2) local nop/oracle/decoy validation (no Harbor runner needed)
bash oddish/tasks/figma-spec-recovery/validate_local.sh     # PASS: nop=0 oracle=1 decoy=0

# 3) with the Oddish runner
oddish run oddish/tasks -a <agent> -m <model> --n-trials 1
```

To author new tasks, use the **`figma-observability-task-builder`** skill.
