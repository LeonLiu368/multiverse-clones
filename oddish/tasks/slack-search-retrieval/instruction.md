# Answer a platform question in the Globex Slack workspace

A teammate has asked a question in the **Globex** Slack workspace and is waiting for an
answer. You have `slack-cli` configured (it talks to the workspace at `$SLACK_API_URL`).

A developer posted this in **#ask-platform**:

> "I need to run a migration test against staging Postgres but I can't find the
> connection details — what's the current hostname and port?"

The answer is documented somewhere in the workspace history. Search for it, for example:

```bash
slack-cli channels list
slack-cli channels history ask-platform --format markdown
slack-cli search "staging postgres" --format markdown
slack-cli search "postgres in:#infra" --format markdown
```

Be careful: there are stale/decoy hosts in the history (a decommissioned legacy host and an
unrelated demo box). Find the **current** staging Postgres hostname **and** port, then post a
single answer to **#ask-platform** that includes it verbatim:

```bash
slack-cli post ask-platform "<the current staging Postgres host:port and any caveat>"
```
