"""slackcli — the agent's Slack tools (a `slack` CLI and a `slack-mcp` MCP server).

Both are thin clients of the Slack Web API served by the gateway at $SLACK_API_URL, exactly the
way real Slack tooling works. The agent never imports slack_sdk or curls the API directly — it uses
these tools, so tool use is consistent across every task.
"""
__all__ = ["client"]
