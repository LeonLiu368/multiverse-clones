# Count assigned issues in Jira

You have a `jira` command-line tool that talks to this team's Jira instance. The project is **WEB**
(Web Frontend). The issue data is only reachable through that tool — it is not on your filesystem.

**Task:** Count how many issues in project **WEB** are currently assigned to **Priya Singh**
(handle `priya.singh`), and write just that number to `/workspace/answer.txt`.

Write your answer to `/workspace/answer.txt` as a single line:

```
count: <number>
```

Tips:
- `jira issue query --assignee priya.singh --json` filters issues by assignee.
- `jira issue list --json` lists issues; `jira --help` lists the available commands.
