# Put the confirmed meeting on the calendar

Your team coordinates scheduling over email. A meeting was confirmed in a Gmail
thread but it is **not on the calendar yet** — please create it.

You have Workspace tools:

- the **`gws-cli`** command (`gws-cli gmail search "<query>"`, `gws-cli gmail thread <threadId> --text`,
  `gws-cli calendar events`, and `gws-cli calendar create -s "<title>" --start <RFC3339> --end <RFC3339>`), and
- the **`gws`** MCP server (incl. `gws_create_event`).

## What to do

1. Find the scheduling thread in Gmail (`gws-cli gmail search`) and read it
   (`gws-cli gmail thread <threadId> --text`).
2. The thread contains a **superseded DRAFT** with a tentative date — **ignore it**.
   Use the **confirmed** message: it gives the exact title, date, and time window.
3. Create the calendar event with that **exact title**, start, and end
   (`gws-cli calendar create` or the `gws_create_event` MCP tool).

The verifier reads the calendar back through the API to confirm your event exists
with the right title and start time.
