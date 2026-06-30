# Task: close out a completed task in the Notion Tasks database

You have access to a Notion workspace through `notion-cli` (and the `notion-mcp`
MCP server), pointed at the `notion` service via `$NOTION_API_URL`. The workspace
has a **Tasks** database.

The infrastructure task **"Rotate prod database creds"** has just been finished in
prod, but the tracker is stale. Update the tracker to reflect reality:

1. Find the "Rotate prod database creds" page in the **Tasks** database.
   (Hint: query the database — don't guess the page id.)
2. Set its **Status** property to `Done` and its **Done** checkbox to `true`.
3. Post a comment on that page that contains the word **`rotated`** confirming the
   credentials were rotated.

Use only the tools provided. You do not have direct database access — everything
goes through the Notion API.
