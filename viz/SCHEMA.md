# Parity-dashboard manifest schema (the contract)

Each clone ships `viz/data/<clone>.json`, produced by a capture script `viz/capture/<clone>.py`
that loads the clone **in-process against its real seed file** and captures its ACTUAL output.
`viz/capture/grafana.py` is the reference implementation — copy its structure.

Two goals, both required:
1. **Verify the seed format is accepted** — the capture must actually load the seed and serve reads.
2. **Capture real clone output** for the comparison boxes (the CLONE column is captured, not authored).

## Manifest top-level
```json
{
  "clone": "<dir name>",
  "product": "Figma",
  "real_service": { "name": "...", "reference": "https://docs...", "api_base": "..." },
  "parity": { "verdict": "HIGH|MEDIUM|LOW ...", "note": "one line, e.g. what the reliability pass fixed" },
  "seed_file": "relative/path/to/seed",
  "surfaces": { "cli": "figma-cli", "mcp": "figma-mcp" },
  "demos": [ <demo>, ... ]
}
```

## `<demo>` — one per capability shown (aim 3–5: a mix of GET reads + ≥1 POST write)
```json
{
  "id": "get-file",
  "title": "Get a file's node tree",
  "method": "GET",                       // or "POST"
  "capability": "Get file (tree+components)",
  "seed_excerpt": { ...small slice of the seed relevant to this demo... },
  "ui": { "type": "<renderer>", ... },   // see renderers below — how the real product shows this data
  "agent": {
    "cli": "figma-cli files get FILEKEY",
    "mcp": { "tool": "figma_get_file", "args": { "key": "FILEKEY" } }
  },
  "real_mapping": {
    "api": "GET /v1/files/{key}",
    "mcp": "figma-mcp › figma_get_file",   // optional
    "cli": "curl -H 'X-Figma-Token: ...'",  // optional
    "doc": "https://www.figma.com/developers/api#files-endpoints"
  },
  "clone_output": <captured actual clone JSON response>,
  "real_output": <golden sample authored from the real API docs — same SHAPE, representative values>,

  // POST demos ONLY — the before/after state so the dashboard highlights the write:
  "change": { "before": [ {id,text|title,tags?} ... ], "after": [ ... ], "new_id": <id of the new item> }
}
```
For POST demos, also set `ui.type`/`ui.before`/`ui.after`/`ui.new_id` OR rely on `change` (the
dashboard renders `change.before` vs `change.after`, highlighting the row whose `id == new_id`).

## UI renderers (`ui.type`) — pick the one that matches the real product's interface
- `list`   → `{type,title, rows:[{icon,title,sub,tags:[]}]}` — search results, issue lists, dashboards
- `chat`   → `{type,title, messages:[{user,color?,ts,text}]}` — Slack channels/threads
- `doc`    → `{type,title, doc_title, blocks:[{type:"h|li|todo|"|"", text}]}` — Notion pages, Google Docs
- `canvas` → `{type,title, nodes:[{type:"TEXT|", name, x,y,w,h}]}` — Figma node tree on a canvas
- `table`  → `{type,title, columns:[...], rows:[{col:val}...]}` — Logfire records, Sentry events, Drive files
      (a column named `level`/`severity` renders as a colored badge: values error|warn|info)
- `chart`  → `{type,title, series:[{name, points:[[x,y]...]}]}` — time series (Grafana/metrics)
- `timeline` → `{type,title, before:[...], after:[{id,text,tags}], new_id}` — annotation/comment writes

## Golden `real_output` rule
Author it from the linked real docs so it has the **same field shape** as `clone_output`
(the dashboard scores response-shape parity: shared field PATHS with matching TYPES). Values
differ — that's expected. Don't fabricate fields the real API doesn't return; if the clone omits a
real field or adds an extra, leave it — the dashboard shows `＋clone`/`＋real` honestly.

## Register the clone
Add a row to `viz/data/index.json` `clones[]`:
`{ "file": "<clone>.json", "product": "Figma", "verdict": "HIGH", "accent": "#f24e1e" }`
