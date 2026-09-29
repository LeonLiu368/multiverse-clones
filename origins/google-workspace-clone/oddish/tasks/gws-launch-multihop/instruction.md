# Wire up the Atlas launch date

The release scheduler needs the **Atlas** launch date in code:

- `/app/launch/plan.py` — `launch_date()` should return the launch date as
  `YYYY-MM-DD`. Right now it returns a placeholder.

The date is **not in the repo**, and it is **not stated outright** in any single
place. You have Google Workspace tools:

- the **`gws-cli`** command — Gmail (`gws-cli gmail search "<query>"`,
  `gws-cli gmail thread <threadId> --text`) and Calendar
  (`gws-cli calendar events -q "<text>"`, `gws-cli calendar get <eventId>`), plus
  Drive/Docs; and
- the **`gws`** MCP server (same operations).

## What to do

There are several "Atlas Launch" holds on the calendar with **different dates**
(tentative, slipped, GA). Which one is authoritative was decided over **email**.

1. Find the launch email thread (`gws-cli gmail search "Atlas launch"`) and read
   it (`gws-cli gmail thread <threadId> --text`). The **final** message from
   release management names which calendar event is the source of truth — but does
   **not** give a date.
2. Look up that event on the calendar (`gws-cli calendar events -q "<event name>"`,
   then `gws-cli calendar get <eventId>`) and read its **start** date.
3. Update `launch_date()` to return that date as `YYYY-MM-DD`.

> Don't shortcut: the earliest email proposes a date that was later overridden,
> and the first calendar hold you find is only tentative. Only the event named in
> the final email is authoritative.

Run the visible checks: `cd /app && python3 -m pytest tests/ -q`.
