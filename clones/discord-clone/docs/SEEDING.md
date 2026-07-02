# Seeding the discord-clone corpus (no server admin required)

The gateway's corpus is built from a **canonical seed dict**
(`{bot_user_id, users, guilds, channels, members, messages}` — see
`src/discordclone/seed/schema.py`). Every producer converges on that shape and reuses
the one load path (`seed/load.py::load_seed` → SQLite), so whatever source you use,
the result is exactly the DB the gateway bakes (`:prod-v1`) or mounts (`:empty`).

There are two kinds of producer:

- **Synthetic** — `generate()` mints a deterministic fake guild (the default corpus).
- **Real-data importers** — three **no-admin** adapters that turn a real Discord
  export into the canonical seed. **None of them requires "Manage Server" or adding a
  bot to a server.**

Build any of them with one command:

```bash
python -m discordclone.seed.build_corpus <SOURCE> --out discord_corpus.db
```

## The three no-admin real sources

### 1. Discord OFFICIAL Data Package  (your own account — no admin)

Discord → **Settings → Privacy & Safety → Request all of my Data**. Discord emails you
a ZIP of *your* account: `account/user.json` plus, per channel you can see,
`messages/<channel_id>/channel.json` (metadata + `guild:{id,name}` for guild channels)
and `messages/<channel_id>/messages.csv` (`ID,Timestamp,Contents,Attachments`). The
exporting user is the single, real author of every message.

```bash
python -m discordclone.seed.build_corpus \
  --from-data-package ./package  --out discord_corpus.db
```

This needs no server permissions at all — it is your own data request.

### 2. Generic public dataset  (HuggingFace / Kaggle — multi-user)

A public Discord conversation corpus as CSV or JSONL, mapped by column. This is the
**multi-user real-conversation** path (best for buried-context tasks — many authors,
real threads of discussion). Snowflakes for guild/channels/users are **synthesized
deterministically** from the source key strings (`ids.stable_snowflake`), so
cross-references resolve and re-imports are byte-identical.

```bash
python -m discordclone.seed.build_corpus \
  --from-dataset ./corpus.csv \
  --map author=user content=text ts=timestamp channel=chan guild=server \
  --out discord_corpus.db
```

`--map` keys: `author` and `content` are **required**; `ts`, `channel`, `guild`, `id`
are optional (sensible defaults when absent). CSV and JSONL are both accepted.

### 3. DiscordChatExporter (Tyrrrz) JSON  (user token OR bot — no admin)

[DiscordChatExporter](https://github.com/Tyrrrz/DiscordChatExporter) exports a channel
to JSON. It works with a **user token** (you export channels you can already read as a
member) *or* a bot token — either way, **no server admin**. The adapter maps ~1:1:
`guild`→guild, `channel`→channel, distinct `messages[].author`→users+members,
`messages`→messages (each `reactions[].users[]`/`count` → `{emoji,user_id}` rows;
`isPinned`→pinned; `timestamp`/`timestampEdited` preserved).

```bash
python -m discordclone.seed.build_corpus \
  --from-dce ./export.json  [--anonymize [--strip-attachments]]  --out discord_corpus.db
```

> **ToS note:** using a **user token** to script Discord (including via
> DiscordChatExporter's user-token mode) is against Discord's Terms of Service and can
> get the account actioned. Prefer exporting only channels you have a legitimate right
> to, use it for offline corpus-building only, and consider a bot token where possible.
> The clone itself never talks to real Discord — it only *reads* an export you already
> produced.

## PII / anonymization

`--anonymize` (default **OFF**) is a one-way, structure-preserving remap:
- every real **user id** → a synthetic snowflake, every **username/global_name** → a
  synthetic handle `user_0001`, `user_0002`, … (stable within the run);
- all references are rewritten (message authors, mentions, member rows, reaction user
  ids, guild owner), so **no real user id or handle survives** (asserted by
  `tests/test_importers.py::test_anonymize_scrubs_user_pii`);
- `--strip-attachments` additionally replaces any `http(s)://…` URLs in message
  content with `[link]`.

Message *content* and timestamps are preserved (that's the signal a task needs);
message ids keep their snowflake-encoded creation time. **Strongly recommended for any
public dataset or user-token DCE export** before baking it into a shipped image.

## Where this runs (operator-only)

The importer + `build_corpus` CLI live in `discordclone.seed`, which is **stripped from
the thin `discord-agent` image** — the agent cannot import them
(`tests/test_isolation.py::test_real_data_importer_not_importable`). Corpus-building is
a gateway/operator step; the agent only ever reads the served corpus over HTTP. Feed
the resulting `discord_corpus.db` to `docker/Dockerfile.prod-v1[.standalone]` (baked)
or mount a canonical-seed JSON into `:empty` via `DISCORD_FIXTURE` (see
`docs/PROD-OVERLAY.md`).

## Reminder

**Adding a bot to a Discord server is NOT required for any of the three paths.** The
Data Package is your own account export; the dataset path is offline public data; the
DCE path works with member-level (user-token) access.
