# Agent tools (discord-clone)

The agent operates the clone through **two surfaces**, both thin clients of the one
HTTP API (`$DISCORD_API_URL`, `Authorization: Bot $DISCORD_BOT_TOKEN`) via the shared
`discordclone.client.DiscordClient`. One capability = one CLI command = one MCP tool.

## `discord` CLI

```
discord users me | guilds | get <user>
discord guilds get <guild> | channels <guild> | members <guild> [--limit --after]
        | member <guild> <user>
        | search <guild> [--content --channel --author --mentions --has --pinned
                          --before --after --limit --offset]
discord channels get <chan> | messages <chan> [--limit --before --after --around]
        | message <chan> <msg> | send <chan> -m "text" | pins <chan>
discord reactions add <chan> <msg> <emoji> | list <chan> <msg> <emoji> [--limit --after]
discord seed generate|load ...      # OFFLINE operator only — not an agent capability
# Real-data corpus builder (operator only; no server admin — see docs/SEEDING.md):
#   python -m discordclone.seed.build_corpus --from-data-package DIR --out discord_corpus.db
#   python -m discordclone.seed.build_corpus --from-dataset FILE --map author=… content=… --out …
#   python -m discordclone.seed.build_corpus --from-dce FILE [--anonymize] --out …
```

## `discord-mcp` (stdio MCP server)

Tools: `discord_get_self`, `discord_list_my_guilds`, `discord_get_user`,
`discord_get_guild`, `discord_get_guild_channels`, `discord_list_members`,
`discord_get_member`, `discord_search_messages`, `discord_get_channel`,
`discord_get_messages`, `discord_get_message`, `discord_send_message`,
`discord_get_pins`, `discord_add_reaction`, `discord_list_reactions`.

Each tool is a pass-through to the identical `DiscordClient` method the CLI uses, so
CLI⇄MCP parity holds by construction (proven in `tests/test_cli_mcp_parity.py`). The
control plane and the offline `seed` commands are never exposed to the agent.
