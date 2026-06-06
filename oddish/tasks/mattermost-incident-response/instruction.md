# Incident response in the Mattermost workspace

You have dropped into the **test-demo** Mattermost workspace as on-call. An incident is
active in **#incidents**. You have **two interchangeable tool surfaces** — use either:

- **`mmctl`** — the official Mattermost CLI, already installed and authenticated (admin).
- **`mattermost` MCP server** — the same capabilities as ~65 structured tools
  (`channel_list`, `post_list`, `post_create`, `channel_create`, `user_search`, …). If your
  runtime loaded it, prefer these tools; otherwise use `mmctl` shell commands.

## Investigate

```bash
mmctl channel list test-demo                          # see the channels
mmctl post list test-demo:incidents -n 50 --show-ids  # read the incident discussion
mmctl post list test-demo:engineering -n 20           # surrounding context
```

## Respond (do all of the following)

1. **Determine the root cause** of the checkout-api latency/5xx incident from the
   discussion in **#incidents**, then **post it to #incidents** as a single message that
   begins with `ROOT CAUSE:` and names the underlying cause:

   ```bash
   mmctl post create test-demo:incidents -m "ROOT CAUSE: <your one-line root cause>"
   ```

2. **Open a dedicated incident channel** named exactly `inc-checkout-latency`:

   ```bash
   mmctl channel create --team test-demo --name inc-checkout-latency --display-name "INC checkout latency"
   ```

3. **Post a status summary** to that new channel. Begin the message with `SUMMARY:` and
   cover the cause and the mitigation:

   ```bash
   mmctl post create test-demo:inc-checkout-latency -m "SUMMARY: <cause> ... <mitigation>"
   ```

Both your `ROOT CAUSE:` message and your `SUMMARY:` message should name the underlying
cause (the database **connection pool** problem).
