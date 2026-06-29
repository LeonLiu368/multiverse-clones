"""slackgw — a task-scoped Slack Web API gateway in front of a real Mattermost backend.

The agent talks to this gateway exactly as it would talk to Slack (Web API methods,
`{"ok": true, ...}` envelopes, `C…`/`U…` ids, `ts` strings, snake_case error codes,
xoxb- bearer token). The gateway translates each call to Mattermost's /api/v4 and returns
Slack-shaped JSON. Mattermost itself is never exposed to the agent — only this gateway is.
"""
