# Oddish tasks — abundant-logfire-clone

Harbor/Oddish agent-eval tasks for the Logfire clone. Each task runs as the canon
two-container **agent + gateway** shape (see the clone root `README.md`).

## `logfire-incident-rca`

Observability + SWE. The `oddish-worker` service is failing in production; a repo test
fails because the `queue_slots` schema is missing the column the worker stamps. The root
cause is recoverable **only from the Logfire telemetry** — the agent must use the
`logfire` CLI / `logfire-mcp` tools to run SQL over the `records` table, find the failing
exception (type, service, table, missing column, occurrence count), fill in the RCA, and
apply the schema fix. A hidden grader pins the exact recovered values.

- **Image:** `logfire-service:prod-v1` (incident corpus baked, served mount-free).
- **Answer:** `asyncpg.exceptions.UndefinedColumnError` / `oddish-worker` / `queue_slots`
  / `locked_at` / `60`.
- **Reward:** `nop=0, oracle=1`.

Layout:

```
logfire-incident-rca/
  task.toml                       # Harbor task manifest (+ logfire-mcp stdio server)
  instruction.md                  # agent-facing prompt
  environment/
    Dockerfile                    # agent (main): logfire-cli + logfire-mcp + codebase, no server.py/data
    logfire.Dockerfile            # gateway built locally (build:+image:), bakes corpus/records.json.gz
    docker-compose.yaml           # main + logfire gateway (healthcheck, no networks:)
    codebase/                     # the repo the agent edits (queue/, incident_rca.py, tests/)
    logfire_clone/ corpus/ entrypoint.sh   # vendored so the gateway builds self-contained
  tests/
    test.sh                       # Harbor entrypoint -> run_verifier.sh
    run_verifier.sh               # grades in an isolated dir; writes /logs/verifier/reward.txt
    trusted/test_grade_rca.py     # hidden grader: exact recovered values + schema fix
  solution/solve.sh               # oracle
```
