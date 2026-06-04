# Slack Web API coverage (v1)

Methods live at `/<base>/api/<method>` (GET or POST; query, JSON, or form params), and return
the Slack envelope `{"ok": true, ...}` / `{"ok": false, "error": "..."}`. Message ids are Slack
`ts` strings (`"<epoch>.<6-digit-seq>"`); threads use `thread_ts`; pagination is cursor-based via
`response_metadata.next_cursor`. **No auth** in v1 (open API on the internal network).

| Method | Implemented | Notes |
|---|---|---|
| `conversations.list` | ✅ | `types`, `exclude_archived`, `cursor`, `limit` |
| `conversations.history` | ✅ | top-level messages only; `oldest`/`latest`/`inclusive`/`cursor`; `has_more` |
| `conversations.replies` | ✅ | parent + replies, chronological |
| `conversations.info` | ✅ | channel metadata (`topic`/`purpose`/`num_members`) |
| `conversations.members` | ✅ | member user ids |
| `chat.postMessage` | ✅ | `text`, optional `thread_ts`; identity via `user`/`SLACK_USER` |
| `chat.update` | ✅ | sets `edited` |
| `chat.delete` | ✅ | tombstones the message |
| `users.list` | ✅ | members with `profile` |
| `users.info` | ✅ | single user |
| `search.messages` | ✅ | substring + `in:#channel` / `from:@user` modifiers; paging |
| `reactions.add` | ✅ | idempotency guard (`already_reacted`) |
| `pins.add` | ✅ | |
| `auth.test` | ✅ | workspace/user identity |

### Not in v1
`files.*`, `chat.scheduleMessage`, real-time events / Socket Mode, Block Kit interactivity,
reactions.remove / pins.remove, DMs/mpims write paths, OAuth scopes & rate limiting. Stored but
not rendered: message `blocks`.

### Message shape (example)
```json
{
  "type": "message", "user": "U0AB12CD3", "text": "rolling back now",
  "ts": "1700000180.000004", "thread_ts": "1700000000.000001",
  "reactions": [{"name": "eyes", "count": 2, "users": ["U…", "U…"]}],
  "edited": {"user": "U…", "ts": "…"}
}
```
A thread parent additionally carries `reply_count`, `reply_users_count`, `latest_reply`.
