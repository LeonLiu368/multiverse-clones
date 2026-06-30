# Close out the checkout bug in Jira

You have a `jira` command-line tool (and a `jira-mcp` MCP server) that talk to this team's Jira
instance. The project is **WEB** (Web Frontend). The issue data is only reachable through those
tools — it is not on your filesystem.

The fix for the **unresponsive Checkout button on mobile Safari** has shipped. Find the WEB issue
that tracks it and close it out:

1. **Transition** that issue to the **Done** state.
2. **Add a comment** on the issue noting the fix shipped.

Then write the issue's identifier to `/workspace/answer.txt` as a single line:

```
issue: WEB-<number>
```

Tips:
- `jira jql "text ~ \"checkout\""` or `jira issue query --assignee <handle>` helps you find issues.
- `jira issue view <ID>` shows an issue; `jira issue transition <ID> "Done"` moves it.
- `jira issue comment add <ID> --body "..."` adds a comment.
- The same operations are available as MCP tools (`search_issues`, `transition_issue`, `add_comment`).
- `jira --help` lists the available commands.
