# Restore the INC-4471 pricing-cache remediation

The `checkout-service` in `/workspace/checkout-service` is misconfigured: a recent
deploy set `PRICING_CACHE_TTL = 0`, which disabled the pricing cache and caused
incident **INC-4471** (a checkout p99 latency spike).

The on-call team already agreed on the fix and recorded the **decision** in the
team's Discord server — but nobody applied it to the repo yet. Your job:

1. **Recover the agreed remediation** from the Discord server. Use the `discord`
   CLI or the `discord-mcp` tools (they talk to the server at `$DISCORD_API_URL`).
   The decision lives in the incident discussion — read the channel history or
   search the guild for `INC-4471` / `PRICING_CACHE_TTL`. It states the exact TTL
   value (in seconds) the team decided to restore.

2. **Fix the code**: set `PRICING_CACHE_TTL` in
   `/workspace/checkout-service/config.py` to that agreed value.

3. **Post a remediation notice** to the guild's **`#deploys`** channel with a
   message that mentions both `INC-4471` and the restored TTL value, e.g.
   `INC-4471 remediation: restored PRICING_CACHE_TTL=<value>`.

You have the `discord` CLI, the `discord-mcp` MCP server, and the codebase. The
Discord workspace is only reachable through those tools — there is no local copy.
