# `slack-service` — drop-in for Harbor/Oddish tasks

Add a seeded Slack workspace to any multi-service task. Two pieces:

1. A **`slack`** service (this image) that serves the Slack-faithful API on `:3000`.
2. Your **client/agent** container with `slack-cli` installed and `SLACK_API_URL=http://slack:3000`.

## Contract

- Mount a seed source into the `slack` service at **`/data/slack`** (read-only). On first
  boot the entrypoint loads it (priority): `slack.db` → `workspace.json` → `export/` (a real
  Slack export dir). If none is present, it generates a synthetic workspace.
- The agent talks to the workspace **only** through `slack-cli` / the HTTP API — it never sees
  the raw seed files (mount the seed into the `slack` service, not the client).
- Verifiers read workspace state back via the API (e.g. `search.messages`, `conversations.history`)
  — never trust agent narration.

## Compose snippet

See [compose-snippet.yaml](compose-snippet.yaml). Author a workspace with the CLI:

```bash
# synthetic
slack-cli seed generate --seed 42 --emit data/slack/workspace.json --out /dev/null
# real export
slack-cli seed import-export ./my-slack-export --emit data/slack/workspace.json --out /dev/null
```

Commit `data/slack/workspace.json` (or a prebuilt `slack.db`, or an `export/` dir) into the task.
