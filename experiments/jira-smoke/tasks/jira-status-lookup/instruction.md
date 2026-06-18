# Look up an issue in Jira

You have a `jira` command-line tool that talks to this team's Jira instance (project **ENG**).
The issue data is only reachable through that tool — it is not on your filesystem.

**Task:** Find issue **ENG-2016** and report two facts about it:

1. its current **status** (the workflow state name, e.g. `To Do`, `In Progress`, `Done`)
2. the **assignee** (the person's display name; if unassigned, write `Unassigned`)

Write your answer to `/workspace/answer.txt` as exactly two lines:

```
status: <status>
assignee: <assignee display name>
```

Tips:
- `jira issue view ENG-2016 --json` prints the issue as JSON.
- `jira --help` lists the available commands.
