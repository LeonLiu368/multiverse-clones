# abundant-discord-clone

A faithful, containerized clone of the **Discord REST API v10** for Harbor/Oddish
agent-eval environments, built to **Clone Standard v1**.

- **Fidelity:** T2 — a handwritten SQLite gateway + a real `messages/search` param
  grammar (`content=&channel_id=&author_id=&mentions=&has=&pinned=&before=&after=`)
  and snowflake message-history pagination.
- **Runtime:** two containers — a thin **`discord-agent`** (tools only, data-free)
  and a **`discord-service`** gateway (the REST API + `discord` CLI + `discord-mcp`),
  published as the image trio `discord-service` / `:empty` / `:prod-v1`.
- **Surfaces (R3):** the `discord` CLI **and** the `discord-mcp` MCP server, both
  thin clients of one HTTP API via the shared `discordclone.client.DiscordClient`.

See `docs/COVERAGE.md` for the capability matrix and `clone-spec.yaml` for the
machine-readable manifest.

## Quick start (local, no docker)

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
discord seed generate --out discord.db          # build a corpus (operator only)
DISCORD_DB=discord.db uvicorn discordclone.api.app:app --port 8080 &
export DISCORD_API_URL=http://localhost:8080 DISCORD_BOT_TOKEN=discord-clone-token
discord users me
discord guilds channels <guild_id>
pytest -q
```

The agent reaches the gateway only over HTTP (`$DISCORD_API_URL`) with a bot token
(`Authorization: Bot $DISCORD_BOT_TOKEN`); it never touches the corpus DB on disk.
