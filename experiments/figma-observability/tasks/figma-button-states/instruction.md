# Ship the Button states to match the design

The design-system **Button** still encodes placeholder state values from before the
design was finalized. Engineering keeps the button's spec in one module:

- `/app/button_states/states.py` — `button_states_spec()` returns the button's spec
  (label, height, padding, radius, default/hover fills, disabled opacity). The values
  there are stale placeholders.

You can run the visible checks with:

```bash
cd /app && python3 -m pytest tests/ -q
```

They confirm the *shape* of the spec but not the actual values — those live in the
**design file**, not the repo.

## The design

The finalized design is in Figma file **`BtnStatesSpecFile0001x`** — a `Button`
component set with **Default**, **Hover**, and **Disabled** states. You have Figma
tools pointed at it:

- the **`figma-cli`** command (e.g. `figma-cli tree <key>`, `figma-cli node <key> <id>`,
  `figma-cli text <key>`, `figma-cli styles list <key>`, `figma-cli comments list <key>`,
  `figma-cli comments add <key> --node <id> -m "…"`), and
- the **`figma`** MCP server (same operations as tools).

This design went through several review rounds, so read carefully — the finalized
spec is **spread across the file** and some of what's drawn on the components is
out of date:

- not every value is written in the comments — some you can only read off the
  components themselves;
- some values are only stated in the comments, not drawn on the components;
- one state's fill is given as a **color token**, and you'll need the **color styles**
  to turn that token into a hex value;
- a couple of comments were superseded by later ones.

Recover the **current, finalized** spec — don't guess, check it against the file.

## What to do

1. Update `/app/button_states/states.py` so `button_states_spec()` returns the
   finalized spec exactly (keep the keys and types as documented in the module).
2. Post a comment on the **Button** component set node in the Figma file summarizing
   the spec you implemented, so the design team has a record.

When the values match the design and the completion comment is posted, you're done.
