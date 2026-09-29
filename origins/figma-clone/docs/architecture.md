# Architecture

One governing commitment (inherited from the `service-clone-builder` pattern):

> **One HTTP API is the single source of truth. The CLI, the MCP server, and the
> verifier are thin clients of that API. The seeded data lives only behind the
> API and mounted on a per-task basis, never in a file the agent can read.**

## Layers

```
canonical seed (JSON)            seed/schema.py  — the single seam
        │
        ▼
seed/{generator,import_file,load}.py → SQLite (figma.db)  via store.upsert_*
        │
        ▼
store.py  — reads/writes + Figma-shaped serialization (the seam shared by API + loader)
        │
        ▼
api/app.py — FastAPI; /v1/* paths, X-Figma-Token, {"status","err"} errors
        ▲
        │ httpx (thin clients)
  ┌─────┴───────────────┐
figma-cli            figma-mcp
(cli/main.py)        (mcp/server.py)
```

`store.py` is imported by both the API and the seed loader, so the bytes the
verifier reads back are produced by the same code that seeded them.

## Why the node tree is the payload

A Figma file is one deeply-nested **document node tree**. 
https://developers.figma.com/docs/rest-api/files/
(`DOCUMENT → CANVAS → FRAME → … → TEXT/RECTANGLE/COMPONENT`). The design spec an
observability task hides — exact `fills` (colors), `characters` (copy), `style`
(typography), `cornerRadius`, `itemSpacing`/`padding*` (spacing), `layoutMode` —
lives in node properties. We store the tree as a JSON column on `File` and serve
it back verbatim; `GET /v1/images` returns URLs to pre-baked placeholder PNGs
because pixels are never graded — the structured values are.

## Derived client helpers

The real Figma API has no search/text-extract endpoints, so `figma-cli`'s
`tree`/`node`/`text`/`search` (and the matching MCP tools) are **client-side
derivations** over `GET /v1/files/{key}`, sharing `store.iter_nodes` /
`store.find_node`. 

## Isolation

- **By secret, not port.** The only privileged surface is `/_control/*`, gated by
  `FIGMA_CONTROL_TOKEN` (constant-time compare; 404 when unset or on mismatch).
- **Per-task data sealing.** A task mounts its `fixture.json` into the *service*
  container only, or pushes it via `/_control/seed`. The agent's container never
  mounts the fixture and never holds the control token, so the seeded spec is
  reachable only through `/v1/*`.
- **Deterministic seeding.** `generate(seed=N)` is byte-identical across runs.
