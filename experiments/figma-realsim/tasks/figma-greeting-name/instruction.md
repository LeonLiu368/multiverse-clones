# Read the name from the design

A small change request: the greeting in our Figma design introduces a name, and we
need that name available in code.

- `/app/whois/whois.py` — `greeting_name()` should return the name the greeting
  introduces. Right now it returns a placeholder.

The name is **in the design file, not in the repo**. You have Figma tools pointed at
the file:

- the **`figma-cli`** command (e.g. `figma-cli tree <key>`, `figma-cli text <key>`,
  `figma-cli node <key> <id>`), and
- the **`figma`** MCP server.

The file key is `BM8JZIS9LbZnEZSUQit8T0` (also in `$FIGMA_FILE_KEY`).

## What to do

1. Read the design file and find the greeting text layer.
2. Update `/app/whois/whois.py` so `greeting_name()` returns exactly the name the
   greeting introduces.

Run the visible checks any time: `cd /app && python3 -m pytest tests/ -q`.
