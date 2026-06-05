# `slack-service` — drop-in for Harbor/Oddish tasks

Add a seeded Slack workspace to any multi-service task. Two pieces:

1. A **`slack`** service (this image) that serves the Slack-faithful API on `:3000`.
2. Your **client/agent** container with `slack-cli` (and optionally the `slack-mcp` MCP
   server) installed and `SLACK_API_URL=http://slack:3000`.

## Contract

- The slack image **bakes in a workspace catalog** (the repo's `workspaces/*.json`). Pick one
  per task by name: set **`SLACK_WORKSPACE=<name>`** on the `slack` service. The data lives in
  the image, **never in the task directory** — so the agent can't read the answer from a file.
- The agent talks to the workspace **only** through `slack-cli` / `slack-mcp` / the HTTP API.
- Verifiers read workspace state back via the API (e.g. `search.messages`,
  `conversations.history`) — never trust agent narration.
- Need to (re)seed a *running* service with your own data? Use the token-gated control plane
  (`POST /_control/seed`), set `SLACK_CONTROL_TOKEN` on the `slack` service, and send a matching
  `X-Control-Token` header. The client container is **never** given the token. See
  [docs/architecture.md](../../docs/architecture.md).

### Legacy escape hatch
If you'd rather mount a one-off seed instead of using the baked catalog, mount it at
**`/data/slack`** (read-only) — `slack.db` → `workspace.json` → `export/`. The catalog
(`SLACK_WORKSPACE`) takes priority; the mount is the fallback.

## Compose snippet

See [compose-snippet.yaml](compose-snippet.yaml). To add a workspace to the catalog, author a
canonical seed and drop it in the repo's `workspaces/`:

```bash
slack-cli seed generate --seed 42 --emit workspaces/my-workspace.json --out /dev/null
# or from a real export:
slack-cli seed import-export ./my-slack-export --emit workspaces/my-workspace.json --out /dev/null
```
Then rebuild the slack image and reference it with `SLACK_WORKSPACE=my-workspace`.
