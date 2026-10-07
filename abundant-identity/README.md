# abundant-identity — shared PERSON IDENTITY REGISTRY

A clone-agnostic cross-reference of person numbers → canonical names/handles so the
**same human is the same named person in every clone** (Slack, Jira, and future
GitHub/Sentry/… clones).

Both the Slack export and the Jira backup anonymize people with the **same token**
`[PERSON_NAME_<N>]`. This registry maps each `N` to one canonical identity record.
Every clone importer extracts `N` from whatever anonymized reference it holds and
adopts the registry's `{handle, display_name, real_name}`.

## Why this exists / the frozen constraint

The Slack prod corpus image (`slack-gateway:prod-v1`) is **already built and frozen**.
Its synthetic names are baked into `prod/v1/catalog/users.json`. We do **not** rebuild
it. Instead this registry **reproduces** those exact names for the people who have a
prod Slack account, and other clones **adopt** them.

The Slack importer (`import_export._assign_synthetic_names`) named a user whose raw id
is `PERSON_<N>_SLACK_ID` by:
1. `h = int(sha1("PERSON_<N>_SLACK_ID"), 16)`
2. `first = FIRST_NAMES[h % 40]`, `last = LAST_NAMES[(h // 40) % 40]`
3. walking the **whole user roster in sorted-id order**, assigning each handle
   `first.last` greedily — so collisions get numeric suffixes (`yara.kowalski`, then
   `yara.kowalski2`, …).

To reproduce a roster member's name **byte-for-byte** we replay that exact sorted
iteration over the exact roster the importer saw. That roster — the 141 published user
ids, including non-`PERSON` real Slack ids and bots that still consume handle slots — is
frozen into `data/prod_v1_slack_roster.json`. The name-pool + collision logic is **copied**
(not imported) into `identity_registry.py`, so this artifact has zero runtime dependency
on the slack repo.

## Layout

```
identity_registry.py            # generator module (clone-agnostic, copies the name logic)
generate_registry.py            # scans Slack export + Jira backup, writes registry.json
registry.json                   # the committed registry (regenerate with generate_registry.py)
test_registry.py                # byte-for-byte reproduction test (the linchpin)
data/prod_v1_slack_roster.json  # frozen 141-id roster the prod importer hashed
```

## The registry record

```json
"14350": {
  "person_id":    "PERSON_NAME_14350",
  "handle":       "yara.kowalski",
  "display_name": "Yara",
  "real_name":    "Yara Kowalski",
  "email":        "yara.kowalski@acme.test",
  "is_bot":       false,
  "sources":      ["slack", "jira"]
}
```

`sources` records which corpora referenced the person, so the cross-corpus overlap is
queryable (`["slack","jira"]` == a shared human). A top-level `_meta` block carries the
counts and the schema id (`abundant-identity/registry@1`).

## Consumption contract (how a clone importer consumes the registry)

```python
import json, re
REG = json.load(open("registry.json"))
PERSON_RE = re.compile(r"PERSON_(?:NAME_)?(\d+)")          # matches every token shape

def resolve(ref):
    m = PERSON_RE.search(ref or "")
    if not m:                                              # not a person token
        return {"handle": "unknown", "display_name": "Unknown",
                "real_name": "Unknown User"}
    rec = REG.get(m.group(1))                              # orphan / unknown N -> fallback
    return rec or {"handle": "unknown", "display_name": "Unknown",
                   "real_name": "Unknown User"}
```

`identity_registry.lookup(REG, ref)` / `extract_person_number(ref)` do exactly this.

The regex matches every anonymized reference shape any clone holds:
`[PERSON_NAME_14350]`, `PERSON_14350_SLACK_ID`, `PERSON_14350_JIRA_KEY`,
`PERSON_14350_NAME`, `PERSON_14350_EMAIL` — all key on the same `N`.

### Unification guarantee

For people in the prod-v1 roster (those with a `PERSON_<N>_SLACK_ID` account), after both
clones adopt the registry:

```
slack.real_name == jira.name      and      slack.handle == jira.handle
```

This is enforced by `test_registry.py::test_byte_for_byte_reproduction` (registry ==
frozen catalog, exactly) plus both clones reading from the same `registry.json`.

### Edge cases

- **Bots** — flagged `is_bot: true`, named `First Bot` / `first-bot`. Roster bots are
  reproduced byte-for-byte (e.g. `yara-bot2`); clones may exclude them from human user
  lists if desired, but they still resolve.
- **Jira-only people** referenced only as `PERSON_<N>_JIRA_KEY` (no Slack presence) — still
  keyed by `N` and given an independent, deterministic name. **Caveat:** Jira's
  `PERSON_<N>_JIRA_KEY` is a *different anonymizer namespace* from the shared
  `[PERSON_NAME_<N>]` token; a JIRA_KEY `N` is **not** guaranteed to be the same human as a
  name-token `N`. The unification guarantee spans the shared `[PERSON_NAME_<N>]` keyspace.
- **People in only one corpus** — get an independent deterministic name (their own
  collision domain). Harmless: no cross-corpus claim is made about them.
- **Orphan / unknown reference** — a `[PERSON_NAME_<N>]` for an `N` not in the registry, or a
  non-person id (`U6W3ZPPRT`), falls back to `Unknown User` / `unknown`.

### Adopting a new clone (GitHub, Sentry, …)

The format is clone-agnostic: extract `N` via `PERSON_(?:NAME_)?(\d+)`, look up the
registry, apply `{handle, display_name, real_name}`. Nothing in the schema is
Slack- or Jira-specific.

## Regenerate

```bash
python generate_registry.py \
  --slack ~/Downloads/slack \
  --jira  ~/Downloads/jira/entities.xml \
  --out   registry.json
python -m pytest test_registry.py -v      # must stay green
```

## Corpus stats (measured from the live corpora)

| metric | value |
| --- | --- |
| Slack `[PERSON_NAME_<N>]` numbers | 27,694 |
| Jira `[PERSON_NAME_<N>]` numbers | 1,575 |
| Jira internal `PERSON_<N>_JIRA_KEY` numbers | 119 |
| **shared overlap (same human, both corpora)** | **420** |
| union (all person records) | 28,940 |
| prod-v1 roster reproduced byte-for-byte | 69 `PERSON_<N>_SLACK_ID` users |

> Note: an earlier session estimated the overlap at ~221. That figure came from a
> `comm -12` over **numerically**-sorted files — `comm` compares lexically, so it
> silently missed matches. The verified set-intersection count is **420**.
