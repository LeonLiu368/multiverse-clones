# Summarize and pin a decision in the Hooli Slack workspace

The team reached a decision in a thread in the **Hooli** workspace and the eng lead asked
for it to be written up and pinned. You have `slack-cli` configured (it talks to the
workspace at `$SLACK_API_URL`).

Find the decision thread in **#design-decisions** and read it, for example:

```bash
slack-cli channels history design-decisions --format markdown
slack-cli thread design-decisions <ts> --format markdown    # read the full thread
```

The thread debates which date-picker library to adopt for the booking flow. Determine what
the team **landed on**, then:

1. Post a single concise summary message to **#design-decisions** that starts with
   `DECISION:` and names the chosen library and the gist of the reasoning.
2. **Pin** that message so newcomers can find it.

```bash
resp=$(slack-cli post design-decisions "DECISION: <chosen library> — <one-line why>")
ts=$(printf '%s' "$resp" | jq -r '.ts')
slack-cli pin design-decisions "$ts"
```
