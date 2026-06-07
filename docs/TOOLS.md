# The agent's tool surface: the Slack Web API

The agent operates the workspace through a **realistic Slack Web API** — the same way real Slack
automation works: HTTP methods like `conversations.history` and `chat.postMessage`, `{"ok":...}`
envelopes, `C…`/`U…` ids, `ts` strings, an `xoxb-` bearer token. There is **no bespoke CLI** (a
custom CLI is itself a simulation tell). Under the hood a small FastAPI gateway (`slackgw/`)
translates each Slack method to a real Mattermost backend; the agent never sees Mattermost.

## How the agent calls it
Configured the real-Slack way, baked into the agent image as env (so every shell/exec has it):

- `SLACK_API_URL` = `http://api`  (a neutral host; the backend sidecar)
- `SLACK_BOT_TOKEN` = `xoxb-…`

```bash
# official SDK (preinstalled)
python3 - <<'PY'
import os
from slack_sdk import WebClient
c = WebClient(token=os.environ["SLACK_BOT_TOKEN"], base_url=os.environ["SLACK_API_URL"] + "/api/")
print([ch["name"] for ch in c.conversations_list()["channels"]])
print(c.search_messages(query="overdue fee")["messages"]["matches"][:3])
c.chat_postMessage(channel="postmortems", text="ROOT CAUSE: ...")
PY

# or curl
curl -s "$SLACK_API_URL/api/conversations.history?channel=C0000000000&limit=50" \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN"
curl -s -X POST "$SLACK_API_URL/api/chat.postMessage" -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
  --data-urlencode channel=postmortems --data-urlencode "text=ROOT CAUSE: ..."
```

## Methods implemented (task-scoped)
| Method | Returns |
|---|---|
| `auth.test` | `{ok, url, team, user, team_id, user_id}` |
| `conversations.list` | `{channels:[{id,name,is_channel,is_private,is_archived,topic,purpose}], response_metadata}` |
| `conversations.info` | `{channel:{…}}` |
| `conversations.history` | `{messages:[{type,user,text,ts}], has_more, response_metadata}` |
| `search.messages` | `{messages:{total, matches:[{type,user,text,ts,channel}]}}` — **noisy on purpose** |
| `users.list` / `users.info` | `{members:[…]}` / `{user:{id,name,real_name,deleted,is_bot,profile}}` |
| `chat.postMessage` | `{ok, channel, ts, message}` |

Fidelity is faithful where agents trip: the envelope (always HTTP 200), id formats, `ts` strings,
cursor fields, and snake_case error codes (`not_authed`, `channel_not_found`, `unknown_method`).

## What the agent CANNOT see (recon hardening)
- **Mattermost is unreachable.** It's bound to `127.0.0.1` inside the `api` sidecar; `curl api:8065`
  → connection refused.
- **No `/api/v4`.** Any non-Slack path (e.g. a probe at `/api/v4/...`) returns Slack-shaped
  `{"ok":false,"error":"unknown_method"}`.
- **No backend/framework headers.** `Server`/`X-Version-Id` are stripped; responses look like a
  generic Slack-compatible endpoint.
- **No service-name tell in URLs** beyond the neutral host `api`; no `:8065`, no Mattermost.

## Minimal hand-holding by design
Instructions tell the agent only the symptom + that it has the Slack Web API (`$SLACK_API_URL` /
`$SLACK_BOT_TOKEN`). It must explore (list channels, read history, search) and **disambiguate**
superseded vs. agreed values — that exploration is the skill being measured.
