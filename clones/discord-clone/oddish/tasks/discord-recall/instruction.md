# Recover the agreed API rate limit from Discord

Your team discussed and agreed on the API-gateway rate limit in the team's Discord
server, in the **`#engineering`** channel — but nobody wrote it down anywhere else.
We need those numbers to configure the gateway.

Find, in the `#engineering` channel discussion, the **agreed per-API-key rate limit**
(in **requests per minute**) and the **burst allowance** the team settled on. Use the
`discord` CLI or the `discord-mcp` tools (they talk to the server at `$DISCORD_API_URL`).
Read the channel history or search the guild for the relevant discussion.

Write your answer to `/workspace/answer.txt` as **exactly two lines**:

```
rate=<requests-per-minute>
burst=<burst-allowance>
```

For example, if the team had agreed on 90 requests/min with a burst of 15, the file
would contain `rate=90` on the first line and `burst=15` on the second.

You have the `discord` CLI, the `discord-mcp` MCP server, and a shell. The Discord
workspace is only reachable through those tools — there is no local copy of the
conversation.
