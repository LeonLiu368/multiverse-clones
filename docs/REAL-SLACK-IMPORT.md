# Importing a real Slack export

This document covers the planned schema changes and importer script needed to turn a real Slack
workspace export into a `scraped.json` file our seeder can consume.

---

## What a real export looks like

```
export/
  channels.json          # [{id, name, purpose, topic, creator, created, …}, …]
  users.json             # [{id, name, real_name, display_name, profile:{…}, …}, …]
  <channel-name>/
    YYYY-MM-DD.json      # array of message objects for that day
```

The channel name is the directory name. The date is in the filename — not in the messages.
Each daily file is a JSON array (no wrapper object). User display names live in embedded
`user_profile` objects, not at the top level. Timestamps are Unix float strings.

---

## Required changes

### 1. `seed.py` — timestamp parsing

**Current**: expects ISO 8601 strings and calls `datetime.fromisoformat(ts)`.

**Change needed**: also accept Unix float strings (`"1646780255.193039"`). The fix is a small
helper at the top of the timestamp block:

```python
def parse_ts(ts: str) -> int:
    """Return milliseconds. Accepts ISO 8601 or Unix float string."""
    try:
        # Unix float: "1646780255.193039"
        return int(float(ts) * 1000)
    except ValueError:
        # ISO 8601: "2024-09-02T09:00:00+00:00"
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
```

Replace the inline `datetime.fromisoformat` block in `main()` with `parse_ts(m.get("timestamp"))`.

### 2. `seed.py` — field name aliases

**Current**: reads `m.get("content")` for text and `m.get("author")` for the user.

**Change needed**: fall back to the real Slack field names so both formats work:

```python
content = (m.get("content") or m.get("text") or "").strip()
author  = (m.get("author")  or
           (m.get("user_profile") or {}).get("display_name") or
           (m.get("user_profile") or {}).get("name") or
           m.get("user") or "anonymous")
```

This keeps the current synthetic format working unchanged while also accepting real exports.

### 3. `seed.py` — skip system messages

Real exports include messages with `subtype: channel_join`, `channel_purpose`, `bot_message`, etc.
These are noise and should be filtered out before seeding:

```python
SKIP_SUBTYPES = {"channel_join", "channel_leave", "channel_purpose", "channel_name",
                 "channel_archive", "channel_unarchive", "bot_message"}

for m in messages:
    if m.get("subtype") in SKIP_SUBTYPES:
        continue
    content = (m.get("content") or m.get("text") or "").strip()
    if not content:
        continue
    # … rest of seeding
```

### 4. `seed.py` — strip Slack markup from text

Real messages contain Slack markup that looks odd in Mattermost:
- `<@U01ABC123>` — user mention
- `<#C01ABC123|channel-name>` — channel mention
- `<https://example.com|link text>` — hyperlink

The gateway returns text as-is from Mattermost, so the agent would see raw markup. Two options:

**Option A (simple)**: Strip all markup to plain text before seeding:
```python
import re

def strip_slack_markup(text: str) -> str:
    text = re.sub(r'<@([A-Z0-9]+)>', r'@\1', text)               # user mention
    text = re.sub(r'<#[A-Z0-9]+\|([^>]+)>', r'#\1', text)        # channel mention
    text = re.sub(r'<([^|>]+)\|([^>]+)>', r'\2', text)            # link with label
    text = re.sub(r'<([^>]+)>', r'\1', text)                      # bare URL
    return text
```

**Option B (fidelity)**: Keep markup as-is — it already looks realistic and agents shouldn't rely
on resolving specific user IDs anyway. The anonymised real exports use placeholder IDs like
`PERSON_14350_SLACK_ID`, which is fine for benchmark purposes.

Recommendation: use Option B for anonymised exports (markup is already sanitised); use Option A if
importing raw real data where user IDs are real Slack IDs.

---

## New: `import_slack_export.py`

A new script (not yet written) that transforms a real Slack export directory into our `scraped.json`
format. Planned interface:

```bash
python3 import_slack_export.py \
  --export-dir /path/to/slack-export/ \
  --output     data/mattermost/scraped.json \
  --channels   5star-squad,general,engineering \   # optional filter
  --start      2022-03-01 \                         # optional date range
  --end        2022-06-01
```

What it does:
1. Reads `users.json` → builds a map from Slack user ID to display name.
2. For each selected channel directory:
   - Reads each `YYYY-MM-DD.json` file in date order.
   - For each message (skipping system subtypes):
     - Resolves `user` ID to display name via the user map.
     - Normalises the timestamp to ISO 8601.
     - Optionally strips Slack markup.
     - Appends `{channel, author, content, timestamp}` to the output list.
3. Writes `{"messages": [...]}` as `scraped.json`.

---

## Scraped.json: no schema change needed for basic import

The internal `scraped.json` schema (`channel`, `author`, `content`, `timestamp`) is already a
sufficient abstraction. The real import just needs to map the real fields into it. Only `seed.py`
changes (field aliases + timestamp parsing + subtype skipping) — the schema file itself stays the
same.

**Optional enrichment** (not required, nice to have later):

| Field | Type | Notes |
|---|---|---|
| `reactions` | `list[str]` | emoji names; gateway could return them in `conversations.history` |
| `thread_ts` | `str` | parent message ts; allows threading in the seeded workspace |
| `files` | `list[str]` | filenames; currently not seeded (MM file attachments complex) |

These are additive. Adding them to `scraped.json` and to `seed.py`'s insert logic would not break
existing synthetic tasks (they just won't have those fields).

---

## Summary of changes

| File | Change | Scope |
|---|---|---|
| `selfcontained/base/seed.py` | `parse_ts()` helper + field aliases + skip subtypes | ~20 lines |
| `selfcontained/base/seed.py` | optional markup stripper | ~10 lines |
| *(new)* `selfcontained/base/import_slack_export.py` | ETL: real export → `scraped.json` | ~100 lines |
| `scraped.json` schema | No breaking change (adds optional fields if enrichment wanted) | — |
| `generate.py` files | No change (still produce the same `{channel,author,content,timestamp}`) | — |

Run `selfcontained/base/vendor.sh` after updating `seed.py` to push the change into all tasks.
