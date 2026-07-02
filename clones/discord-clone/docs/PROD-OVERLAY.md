# Prod overlay + seeding paths (discord-clone)

The `discord-service` gateway carries data one of two ways (both required to exist,
per the canon). Switching a task between them is the **image tag alone**.

## 1. Baked-DB (GHCR image DB seeding) — `discord-service:prod-v1`

The prod corpus (`discord_corpus.db`) is baked into the image
(`COPY discord_corpus.db /srv/discord.db`). The entrypoint sees an existing
`$DISCORD_DB` and serves it **as-is with no seeding and no mount**. This is the
realistic path most tasks use — the "Acme Engineering" guild with the INC-4471
incident discussion. Verify:

```bash
docker run --rm -p 8080:8080 ghcr.io/abundant-ai/discord-service:prod-v1 &
curl -s -H "Authorization: Bot t" localhost:8080/users/@me/guilds   # returns the seeded guild
```

## 2. Empty + mount — `discord-service:empty`

The base API with **no corpus**. A task supplies its own guild by mounting a
canonical seed JSON into the **gateway** (`-v ./fixture.json:/srv/fixture.json`,
`DISCORD_FIXTURE=/srv/fixture.json`) or pushing it through the token-gated
`/_control/seed` control plane (`DISCORD_CONTROL_TOKEN`, operator-only). The fixture
is mounted into the gateway **only**, never the agent, so the agent still reaches
state exclusively over HTTP.

### Canonical seed shape

See `src/discordclone/seed/schema.py`. A seed is a plain JSON doc
(`{bot_user_id, users, guilds, channels, members, messages}`) that a hand-authored
fixture, the deterministic synthetic generator, and (in future) a real export all
emit identically, so `discord seed load` writes it to SQLite the same way. Bulk =
this native format; runtime mutations (send message, add reaction) go through the
shared op-list in `store.py`.

## Determinism (R1.6)

`discord seed generate --seed N` mints byte-identical ids/timestamps for a given
seed via a deterministic `Snowflake` clock + a seeded `random.Random`, so a rebuilt
corpus is reproducible.
