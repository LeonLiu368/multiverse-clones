# Figma REST API coverage

Faithful to the real [Figma REST API](https://www.figma.com/developers/api). Auth
mirrors the personal-access-token header `X-Figma-Token` (or `Authorization:
Bearer …`); a non-empty token is accepted (presence == valid, like a real PAT).
Errors mirror Figma's `{"status": <code>, "err": "<message>"}` body with the
matching HTTP status.

| Method | Endpoint | Notes |
|---|---|---|
| GET | `/v1/files/{key}` | Full document tree + `components`/`componentSets`/`styles`/`schemaVersion`. Supports `?ids=` (returns `nodes` map) and `?depth=`. |
| GET | `/v1/files/{key}/nodes?ids=1:2,1:3` | Per-node `{document, components, styles, …}`. Hyphen form `1-2` accepted. |
| GET | `/v1/files/{key}/comments` | `{comments: [...]}` with `client_meta.node_id`, `order_id`, `user`. |
| POST | `/v1/files/{key}/comments` | Body `{message, client_meta?, comment_id?}`. **Agent write surface.** New comment gets a millisecond-epoch `id` (unambiguously "new" vs seeded). |
| DELETE | `/v1/files/{key}/comments/{id}` | |
| GET | `/v1/files/{key}/components` | `{meta: {components: [...]}}`. |
| GET | `/v1/files/{key}/component_sets` | `{meta: {component_sets: [...]}}`. |
| GET | `/v1/files/{key}/styles` | `{meta: {styles: [...]}}` — color/text/effect tokens. |
| GET | `/v1/files/{key}/versions` | `{versions: [...], pagination}`. |
| GET | `/v1/images/{key}?ids=…&format=png&scale=2` | `{err: null, images: {node_id: url}}`. Unknown node → `null`. URLs serve a placeholder PNG from `/static/`. |
| GET | `/v1/teams/{team_id}/projects` | `{name, projects: [...]}`. |
| GET | `/v1/projects/{project_id}/files` | `{name, files: [...]}`. |
| GET | `/health`, `/v1/me` | meta |
| POST/GET | `/_control/{seed,reset,status}` | **token-gated** operator surface (not Figma API) |

## Node properties we preserve

The shapes an agent reads to recover a spec:

- `type` — `DOCUMENT`/`CANVAS`/`FRAME`/`GROUP`/`COMPONENT`/`INSTANCE`/`TEXT`/`RECTANGLE`
- `id`, `name`, `children`
- `characters` — TEXT copy
- `fills` / `strokes` — `[{type:"SOLID", color:{r,g,b,a}}]` (0–1 floats, like Figma)
- `style` — `fontFamily`, `fontWeight`, `fontSize`, `lineHeightPx`, `letterSpacing`, `textAlignHorizontal`
- `cornerRadius`
- `layoutMode` / `itemSpacing` / `paddingLeft|Right|Top|Bottom` / `primaryAxisAlignItems` / `counterAxisAlignItems`
- `absoluteBoundingBox` — `{x, y, width, height}`

## Intentionally out of scope

Write endpoints beyond comments (Figma's REST API itself is read-mostly — there is
no "edit node" REST endpoint), webhooks, dev-resources, and OAuth flows. The
seeded file is authored/imported; agents read it and post comments.
