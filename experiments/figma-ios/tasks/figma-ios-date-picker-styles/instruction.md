# Read the date & time picker styles from the design

We need the list of **date & time picker styles** the design system defines, in code.

- `/app/ios_components/comp.py` — `date_picker_styles()` should return that list. It returns `[]` now.

The values are **in the Figma design, not the repo**. You have the `figma-cli`
command and the `figma` MCP server. The file key is `R1jno9FuCgYkNXayz8zglW` (`$FIGMA_FILE_KEY`).

## What to do
1. Find the component set named **"Date and time - Pickers"** in the design
   (`figma-cli search "$FIGMA_FILE_KEY" "Date and time - Pickers"`), then inspect its
   variants (`figma-cli node "$FIGMA_FILE_KEY" <node-id>`).
2. Update `date_picker_styles()` to return each variant's value (the part after `=` in the
   variant name). Order doesn't matter.

Run the visible checks: `cd /app && python3 -m pytest tests/ -q`.
