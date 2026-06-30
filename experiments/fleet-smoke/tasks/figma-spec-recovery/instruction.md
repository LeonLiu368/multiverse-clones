# Ship the PricingCard to match the design

The marketing site's **PricingCard** component is still showing placeholder values
from before the design was finalized. Engineering keeps the card's spec in one
module:

- `/workspace/pricing_card/card.py` — `pricing_card_style()` returns the card's
  spec (heading, price, padding, gap, radius, CTA label/color/radius). The values
  there are stale placeholders.

You can run the visible checks with:

```bash
cd /workspace && python3 -m pytest tests/ -q
```

They confirm the *shape* of the spec but not the actual values — those live in the
**design file**, not the repo.

## The design

The finalized design is in Figma file **`Pr1cingCardSpecFile001`**. You have Figma
tools pointed at it:

- the **`figma-cli`** command (e.g. `figma-cli tree <key>`, `figma-cli node <key> <id>`,
  `figma-cli text <key>`, `figma-cli comments list <key>`, `figma-cli styles list <key>`,
  `figma-cli comments add <key> --node <id> -m "…"`), and
- the **`figma`** MCP server (same operations as tools).

Use them to read the `PricingCard` component, its child nodes, and the **comment
thread** on the file. The design went through review, so read carefully: some
earlier comments were superseded by later decisions, and at least one value shown
on a node was changed in a later comment. Recover the **current, finalized** spec —
don't guess, check it against the file.

## What to do

1. Update `/workspace/pricing_card/card.py` so `pricing_card_style()` returns the
   finalized spec exactly (keep the keys and types as documented in the module).
2. Post a comment on the **PricingCard** node in the Figma file summarizing the
   spec you implemented, so the design team has a record.

When the values match the design and the completion comment is posted, you're done.
