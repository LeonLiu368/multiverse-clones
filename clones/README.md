# Clones

Vendored source for every service **clone** in the [`abundant-ai`](https://github.com/abundant-ai)
org — the faithful, containerized stand-ins for real SaaS APIs (Slack, GitHub, Figma, …)
that agent-eval tasks run against.

Each subdirectory is the **full source** of one clone, copied from upstream `main` with its
own `.git` removed (vendored, not a submodule). Provenance — the exact upstream commit each
folder was taken from — is pinned in [`MANIFEST.json`](MANIFEST.json). To re-sync a clone,
re-pull from the repo/commit recorded there and replace the folder.

## Inventory

| Clone | Stands in for | Canonical build | "General" compose (base, not per-task) |
|---|---|---|---|
| [`abundant-slack-clone`](abundant-slack-clone) | Slack Web API | `selfcontained/base/Dockerfile*` | ✅ `selfcontained/base/docker-compose.yaml` |
| [`gh-cli-clone`](gh-cli-clone) | GitHub (`gh` CLI + MCP, Forgejo-backed) | `selfcontained/Dockerfile*` | ✅ `docker/docker-compose.yml`, `selfcontained/isolated/docker-compose.yaml` |
| [`figma-clone`](figma-clone) | Figma REST API | `docker/Dockerfile{,.agent,.prod-v1}` | ⚠️ per-task only (`oddish/tasks/*/environment`) |
| [`google-workspace-clone`](google-workspace-clone) | Gmail / Calendar / Drive | `docker/Dockerfile{,.agent,.prod-v1}` | ⚠️ per-task only (`oddish/tasks/*/environment`) |
| [`abundant-jira-clone`](abundant-jira-clone) | Jira / Linear issue tracker | `selfcontained/base/Dockerfile*`, `linear/Dockerfile` | ⚠️ per-task only (`tasks/*/environment`) |
| [`abundant-logfire-clone`](abundant-logfire-clone) | Pydantic Logfire observability | `Dockerfile`, `Dockerfile.agent` | ❌ none |
| [`grafana-clone`](grafana-clone) | Grafana HTTP API (+ Loki / Prometheus query APIs) | `Dockerfile.service` | ✅ `examples/docker-compose.yaml` |
| [`sentry-clone`](sentry-clone) | Sentry | `Dockerfile.service` | ✅ `examples/docker-compose.yaml` |
| [`aws-clone`](aws-clone) | AWS APIs (S3 / Kinesis / IAM …) | `Dockerfile.service`, `Dockerfile.tools` | ✅ `examples/docker-compose.yaml` |

Legend: ✅ ships a base-level compose for standing the clone up • ⚠️ only ships
per-task compose files • ❌ ships none.

`abundant-jira-clone` is built on the **ticketvector** issue service + `jira` CLI;
ticketvector is clone-shaped but not yet vendored here (see scope notes).

## Conventions across clones

Layouts differ by clone, but the recurring pieces are:

- **Service image** — the clone's HTTP API (e.g. `Dockerfile`, `Dockerfile.service`,
  `selfcontained/base/Dockerfile.service`). Holds seeded data the agent cannot read from disk.
- **Agent image** — the harness/agent side with the CLI + MCP tools that are thin clients of
  the service API (e.g. `Dockerfile.agent`).
- **Per-task environments** — `*/tasks/<task>/environment/{Dockerfile,docker-compose.yaml}`,
  a concrete two-container setup wiring one task's seed data to the service + agent.

## Scope notes

- This folder holds repos whose **name or description** identifies them as a clone.
- Excluded as *tooling about* clones (not clones themselves): `org-slice-warehouse`,
  `seed-dashboard`, `task-env-reviewer`.
- `ticketvector` (CLI-first Jira/Linear tracker) is clone-shaped but does not say "clone" in
  its name/description, so it is **not** vendored here yet — flag if it should be.
