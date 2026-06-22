# Read the Header prominence levels from the design

We need the list of **Header prominence levels** the design system defines, in code.

- `/app/ios_components/comp.py` — `header_prominence_levels()` should return that list. It returns `[]` now.

The values are **in the Figma design, not the repo**. You have the `figma-cli`
command and the `figma` MCP server. The file key is `R1jno9FuCgYkNXayz8zglW` (`$FIGMA_FILE_KEY`).

## What to do
1. Find the component set named **"Header"** in the design
   (`figma-cli search "$FIGMA_FILE_KEY" "Header"`), then inspect its
   variants (`figma-cli node "$FIGMA_FILE_KEY" <node-id>`).
2. Update `header_prominence_levels()` to return each variant's value (the part after `=` in the
   variant name). Order doesn't matter.

Run the visible checks: `cd /app && python3 -m pytest tests/ -q`.
