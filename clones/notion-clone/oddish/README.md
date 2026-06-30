# Oddish tasks for notion-clone

Each task is a two-container **agent + gateway** Harbor task: `main` (the agent,
built from `environment/Dockerfile`, neutral base, no data) + `notion` (the gateway,
`notion-service:prod-v1` with the corpus baked in). The agent operates the workspace
through `notion-cli` / `notion-mcp` over HTTP; the verifier reads state back through
the same API and writes `/logs/verifier/reward.txt`.

## Tasks

### `notion-db-triage` — write→read round-trip (assessment-grade)

The agent must **query** the Tasks database to find the "Rotate prod database creds"
page, **update** its `Status` → `Done` and `Done` → `true`, and **create** a
confirmation comment containing "rotated". The verifier
(`tests/run_verifier.sh`) recomputes ground truth by querying the API and checking
all three. Exercises `databases.query` + `pages.update` + `comments.create`.

- `task.toml`, `instruction.md`
- `environment/{Dockerfile, notion.Dockerfile, docker-compose.yaml, notionclone/, notion_corpus.db}`
- `tests/{test.sh, run_verifier.sh}` — `test.sh` → `reward.txt`
- `solution/solve.sh` — the oracle
- `validate_local.sh` — no-docker nop/oracle check (uses the clone's venv)

**Validated:** `nop = 0.0`, `oracle = 1.0`, both locally and in the full
two-container docker shape (gateway serves the baked corpus by service name; the
data-free agent reaches it over HTTP; isolation holds — no corpus on the agent disk).

```bash
# from the clone root, in the project venv:
bash oddish/tasks/notion-db-triage/validate_local.sh
```
