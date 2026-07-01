# Parity Dashboard (`viz/`)

A static dashboard that demonstrates each clone has **parity with the real service**. For every
clone and every demo capability it shows the four panels:

1. **Seed data → real-product UI** — a slice of the clone's seed, rendered the way the real product's
   interface shows it (Grafana chart, Slack channel, Notion page, Figma canvas, Sentry issue table, …).
2. **What an agent runs** — the CLI command and the MCP tool call.
3. **Maps to · real service** — the real API/CLI/MCP endpoint it corresponds to, with a docs link.
4. **Output** — for **GET**: the real API's golden output vs the clone's *captured* output, with a
   field-path **response-shape parity** score. For **POST**: the before/after state with the new row
   highlighted (write→read round-trip), plus the clone's write response vs the real shape.

## Run it
```bash
cd viz && python3 -m http.server 8770
# open http://localhost:8770
```

## How the data is produced (and why it's trustworthy)
Each `capture/<clone>.py` loads that clone **in-process against its real seed file** and calls the
same functions the HTTP API calls, capturing the **actual** response into `data/<clone>.json`. So:
- The **CLONE** column is real captured output — running the capture also **verifies the seed format
  is accepted** (if it loads and serves, the format is good).
- The **REAL** column is a golden sample authored from the linked real-API docs, with the same field
  shape. Values differ (expected); the dashboard scores shared field-*paths* with matching *types*.

Regenerate a clone's data:
```bash
python3 viz/capture/<clone>.py     # e.g. grafana, sentry, logfire, slack, figma, notion, gws
```

## Files
- `index.html` / `app.js` / `styles.css` — the single-page dashboard + renderers.
- `data/index.json` — the clone list (product, verdict, accent).
- `data/<clone>.json` — per-clone manifest (captured).
- `capture/<clone>.py` — the in-process capture script.
- `SCHEMA.md` — the manifest contract (read before adding a clone).

## Coverage
Grafana · Sentry · Logfire · Slack · Figma · Notion · Google Workspace (7 clones, 27 demos).
The external-engine clones (gh-cli/Forgejo, jira/ticketvector, aws/LocalStack) capture live only with
their gateway container running — a follow-up (`capture/<clone>.py` would boot the container).
