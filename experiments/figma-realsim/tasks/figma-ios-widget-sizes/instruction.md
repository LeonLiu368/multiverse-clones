# Read the widget sizes from the design

We're building a Home Screen widget picker and need the list of sizes the design
supports. The design is in Figma; the repo only has a placeholder.

- `/app/ios_widgets/widgets.py` — `home_screen_widget_sizes()` should return the list
  of Home Screen Widget sizes defined in the design. Right now it returns `[]`.

The sizes are **in the design file, not the repo**. You have Figma tools pointed at it:

- the **`figma-cli`** command (e.g. `figma-cli tree <key>`, `figma-cli search <key> "<text>"`,
  `figma-cli node <key> <id>`), and
- the **`figma`** MCP server.

The file key is `R1jno9FuCgYkNXayz8zglW` (also in `$FIGMA_FILE_KEY`).

## What to do

1. Find the **iPhone** "Home Screen Widgets" component set in the design (try
   `figma-cli search "$FIGMA_FILE_KEY" "Home Screen Widgets"`), then inspect its
   variants (`figma-cli node "$FIGMA_FILE_KEY" <node-id>`).
2. Update `/app/ios_widgets/widgets.py` so `home_screen_widget_sizes()` returns the
   size of each variant (the part after `Size=` in each variant's name). Order doesn't
   matter.

Run the visible checks any time: `cd /app && python3 -m pytest tests/ -q`.
