# pull-smoke — the image-pull pattern (no source left behind)

Proves a task can run with **zero clone source in `environment/`** by pulling everything from upstream
GHCR. This is the end-state of "get the images upstream so we don't have source code or images left
behind."

## The task: `tasks/notion-pull/`
Same read+write Notion task as `notion-db-triage`, but its `environment/` contains **only two files**:
```
environment/
  Dockerfile          # FROM ghcr.io/abundant-ai/notion-agent:latest   (tools only; no server/seed source)
  docker-compose.yaml # notion: image: ghcr.io/abundant-ai/notion-service:prod-v1  (PULLED, no build:)
```
No `notionclone/` package, no `notion_corpus.db`, no gateway Dockerfile — the corpus is baked into the
pulled `:prod-v1` image, and the CLI/MCP/client come from the pulled `notion-agent`.

## Upstream images (pushed to abundant-ai)
| Image | Role |
|---|---|
| `ghcr.io/abundant-ai/notion-service:latest` / `:empty` / `:prod-v1` | gateway trio (`:prod-v1` bakes the corpus) |
| `ghcr.io/abundant-ai/notion-agent:latest` | thin agent — `notion-cli` + `notion-mcp` + `notionclone.client`, `api/`+`seed/` stripped |

Each carries `org.opencontainers.image.source` pointing at this repo.

## Verified (local run, pulling from abundant-ai)
- `environment/` = 2 files, no clone source.
- gateway pulled `:prod-v1`, healthy; agent reaches it at `http://notion:3000`.
- agent isolation holds: `notion-cli` works, `import notionclone.client` works, `import notionclone.seed`
  **raises**, no `/srv/notion.db` on the agent.
- **nop = 0.0, oracle = 1.0.**

## Generalizing
`publish-images.yml` now publishes each clone's gateway trio **and** a thin `<svc>-agent` (where a
Dockerfile.agent exists: notion, figma, gworkspace, logfire) to `ghcr.io/abundant-ai`. Once a clone's
agent + `:prod-v1` are published, its task `environment/` can be reduced to this 2-file shape and the
vendored source deleted.
