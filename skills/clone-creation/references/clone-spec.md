# The clone spec — the creator→auditor handoff manifest

Every clone ships a **`clone-spec.yaml`** at its root. It's the machine-readable declaration of what
the clone *claims* to be; `clone-audit` reads it to orient (which images to boot, where the coverage
matrix is, what tier was targeted) and then **verifies the claims**. A missing, stale, or false spec
is itself an audit action item — the spec is part of the contract (R7 input, R2.i).

Keep it short and truthful. Declared ≠ verified: the auditor records `observed` values and flags
divergence (e.g. you declare T2 but expose no query grammar → `observed: T1`, R5 action item).

## Schema (informal)

```yaml
clone: figma-clone                      # folder name
service: Figma REST API                 # real product cloned
standard_version: clone-standard-v1
fidelity_tier: T1                       # T0..T3 (declared); auditor records observed
backed_by: handwritten                  # "handwritten" | "oss:<engine>" e.g. oss:forgejo, oss:localstack

# The two runtime containers: agent (built) + gateway (pulled/seeded).
gateway:                                # the service sidecar = the gateway image trio (R2.a–b)
  registry: ghcr.io/abundant-ai
  base:  figma-service                  # API + CLI/MCP tools, NO data
  prod:  figma-service:prod-v1          # corpus DB baked into the image (R2.j)
  empty: figma-service:empty            # no data, a mount target
  port: 3000
  arches: [linux/amd64, linux/arm64]    # multi-arch publish (R2.k)
  build_image_dual: true                # service has build:+image: so it tags locally, no creds (R1.5)
agent:                                  # `main`, built by Harbor (R2.c)
  built_from: environment/Dockerfile
  base: python:slim                     # neutral base — no gateway artifacts beyond the tools
  data_free: true

seeding:                                # how the gateway gets its DB (R2.j) — BOTH paths must exist
  baked_db:                             # GHCR image DB seeding (the headline path)
    image: figma-service:prod-v1
    corpus_copy: "COPY figma_corpus.db /srv/figma.db"
    serves_mount_free: true             # boots & serves the corpus with NO fixture mount
  mount:                                # empty + per-task fixture
    image: figma-service:empty
    fixture_env: FIGMA_FIXTURE          # mounted into the GATEWAY only, never the agent
    control_plane: /_control/seed       # token-gated alt path

run:                                    # how the auditor stands it up (R1)
  compose: oddish/tasks/figma-spec-recovery/environment/docker-compose.yaml
  service_name: figma                   # gateway name the agent reaches over HTTP
  health_url: http://figma:3000/health
  agent_service: main
  env: [FIGMA_TOKEN]                    # documented env vars; nothing else needed to boot

isolation:
  agent_state_path: /data/figma/state.json   # MUST NOT exist in the agent container (R2.g/c)
  networks_exception: null                   # null, or a note justifying a 'networks:' block (R1.4)

surfaces:                               # R3 — both required, both thin clients of one HTTP API
  http_api: src/figmaclone/api         # the single source of truth
  shared_client: src/figmaclone/client.py
  cli:  { name: figma-cli, entry: "figmaclone.cli.main:app", commands: 20 }
  mcp:  { name: figma-mcp, entry: "figmaclone.mcp.server:main", tools: 11 }

coverage_matrix: docs/COVERAGE.md       # R4 — capability → endpoint+CLI+MCP+envelope+grade
assessment_grade_count: 6               # R5 — capabilities labelled assessment-grade (need ≥5 / ≥3 small)
round_trip_task: oddish/tasks/figma-spec-recovery   # exercises a write→read round-trip (R5.2)

tests:
  suite: tests/                         # R6 — covers every endpoint/CLI/MCP + parity + isolation
  cold_boot: true
  nop_oracle_task: oddish/tasks/figma-spec-recovery   # where nop=0 / oracle=1 is checked (R1.3)

operator_only:                          # capabilities deliberately NOT exposed to the agent (R2.g)
  - seed.generate
  - seed.import-file
```

## How the two skills use it
- **`clone-creation`** writes it as the last build step (step 7) and keeps it current as the clone
  evolves. It's the checklist that the build actually hit every gate.
- **`clone-audit`** reads `gateway.*`/`run.*` to boot the agent+gateway pair, `seeding.*` to run the
  baked-DB (`:prod-v1`, R2.j) and mount probes, `surfaces.*` to enumerate CLI/MCP, `coverage_matrix`
  for the target list, `isolation.*` for the seal check, and `tests.*` to find the suite — then writes
  `audit-verdict.json` with `fidelity_tier.{declared,observed}` and per-requirement results.

## Registering an authored (non-vendored) clone
`clones/MANIFEST.json` was built for **vendored** clones (it requires an upstream `repo` + `commit`).
A clone you **author in-tree** has neither. Register it with an `authored-in-tree` strategy and null
provenance so the manifest stays complete:
```json
"notion-clone": { "strategy": "authored-in-tree", "repo": null, "commit": null, "spec": "clone-spec.yaml" }
```

## Minimum viable spec
If you only fill part of it, fill: `gateway.{base,prod,empty,port}`, `agent.built_from`,
`seeding.baked_db`, `run.*`, `surfaces.{cli,mcp}`, `coverage_matrix`, `isolation.agent_state_path`.
Those are what the auditor needs to boot the agent+gateway pair and probe seeding; the rest sharpens
the verdict and shortens the loop.
