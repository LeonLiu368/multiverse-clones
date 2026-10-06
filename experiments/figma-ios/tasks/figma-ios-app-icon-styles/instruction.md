# Read the App Icon styles from the design

We need the list of **App Icon styles** the design system defines, in code.

- `/app/ios_components/comp.py` — `app_icon_styles()` should return that list. It returns `[]` now.

The values are **in the Figma design, not the repo**. You have the `figma-cli`
command and the `figma` MCP server. The file key is `R1jno9FuCgYkNXayz8zglW` (`$FIGMA_FILE_KEY`).

## What to do
1. Find the component set named **"App Icon/iPhone"** in the design
   (`figma-cli search "$FIGMA_FILE_KEY" "App Icon/iPhone"`), then inspect its
   variants (`figma-cli node "$FIGMA_FILE_KEY" <node-id>`).
2. Update `app_icon_styles()` to return each variant's value (the part after `=` in the
   variant name). Order doesn't matter.

Run the visible checks: `cd /app && python3 -m pytest tests/ -q`.
