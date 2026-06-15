# Pick up your assigned ticket

You have a Linear ticket assigned to you. Start there:

```bash
linear issue mine --json          # find what's on your plate
linear issue view DES-101 --comments --json
```

The ticket asks you to implement the **PricingCard** component to match a finalized
design. The design itself is **not in the repo** — the ticket points you at a Figma
file. You have Figma tools for it:

- the **`figma-cli`** command (`figma-cli tree <key>`, `figma-cli node <key> <id>`,
  `figma-cli text <key>`, `figma-cli comments list <key>`, …), and
- the **`figma`** MCP server (same operations).

Engineering keeps the card's spec in one module:

- `/app/pricing_card/card.py` — `pricing_card_spec()` returns the card's spec (heading,
  price, padding, radius, CTA label). The values there are stale placeholders.

Run the visible checks any time with `cd /app && python3 -m pytest tests/ -q` (they
check the *shape* of the spec, not the values).

## What to do

1. Read the ticket and the design file. The finalized values are in the Figma
   `PricingCard` component and its **comment thread** — read carefully, because the
   copy drawn on the mock may be out of date and superseded by a later comment.
2. Update `/app/pricing_card/card.py` so `pricing_card_spec()` returns the finalized
   spec exactly (keep the keys and types as documented in the module).
3. Move the ticket **DES-101** to **In Review**, and add a comment listing the values
   you implemented, so the team has a record.

You're done when the code matches the design, the ticket is In Review, and your
comment is on the ticket.
