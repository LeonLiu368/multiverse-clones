# Importing a real Slack export

The seed format **is** the real Slack export format, and `import_export.py` ingests it directly into
the gateway's SQLite store with full fidelity (timestamps, user ids/profiles, threads, reactions,
subtypes). This is implemented and used by every task — not a future plan.

## What a real export looks like
```
export/
  channels.json          # [{id, name, created, creator, is_archived, is_general, members, topic, purpose}, …]
  users.json             # [{id, team_id, name, real_name, deleted, is_bot, tz, profile:{display_name, email, …}}, …]
  <channel-name>/
    YYYY-MM-DD.json      # array of message objects for that day
```
Each message: `{user, type, subtype?, ts (Unix float string), text, client_msg_id?, team?,
user_profile:{name, real_name, display_name, …}, blocks?, reactions?, thread_ts?, reply_count?,
edited?}`. Channel name is the directory name; the date is the filename. Timestamps are Unix float
strings, not ISO 8601. Display names live in `user_profile`, not the top level.

## The importer — `selfcontained/base/import_export.py`
```bash
python3 import_export.py --export-dir <dir> [--channels a,b,c] [--start YYYY-MM-DD] [--end ...]
python3 import_export.py --scraped <scraped.json>        # legacy {channel,author,content,timestamp}
# env: SLACK_DB (default /tmp/slack.db)
```
It is robust to **both** export variants:
- **Complete export** (`channels.json` + `users.json` present) — uses them as authoritative.
- **Anonymized export** (top-level files stripped, e.g. the 3.2 GB corpus) — derives channels from
  the subdirectory names and users from each message's `user` + embedded `user_profile`.

It also **normalizes any non-Slack-shaped id** (`PERSON_*`, `UANON*`, raw mixed ids) to deterministic
`C…`/`U…` ids via a stable map, so the off-the-shelf korotovsky MCP (which expects Slack id shapes)
works. System-subtype messages (`channel_join`, etc.) are skipped; threads/reactions are preserved.
`--channels`/`--start`/`--end` carve a manageable slice out of a huge corpus.

## Two ways to author a task seed
1. **Synthetic, written as export shape (default).** `generate.py` builds the story + planted fact
   as `{channel, author, content, timestamp}` dicts and calls
   [`slack_export_writer.write_export`](../selfcontained/base/slack_export_writer.py), which emits a
   real export directory under `data/slack-export/` (deterministic `C…`/`U…` ids, Slack `ts`
   strings, embedded `user_profile`, optional threads via a `thread_key`). Committed.
2. **Sampled from a real corpus.** Run `import_export.py --export-dir <corpus> --channels … --start
   … --end …` to carve a slice, then inject the planted thread. Use this when you want genuine
   real-world noise. Never commit a multi-GB corpus — commit only the carved slice.

## Boot
`slack-boot.sh` imports the seed at container start: `/data/slack-export` (a real export) first, then
a legacy `scraped.json`. The gateway then serves Slack Web API responses from SQLite — `conversations.history`
includes `thread_ts`/`reactions`, `conversations.replies` returns threads, `search.all`/`search.messages`
cover search. The agent reads it identically whether the seed was synthetic-as-export or sampled real data.
