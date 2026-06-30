# Coverage matrix — `figma-clone`

Machine-checkable map of the real Figma REST API's **agent-used surface** to this
clone's endpoint + `figma-cli` command + `figma-mcp` tool, with envelope-fidelity,
assessment-grade label, and test status. One row per capability. Auth mirrors
Figma's `X-Figma-Token` PAT header; errors mirror `{"status","err"}` with the
matching HTTP code. See `figma-api-coverage.md` for endpoint notes and the node
property set; see `architecture.md` for the agent+gateway shape.

| Capability | Endpoint | CLI | MCP | Envelope | Assessment-grade | Tested |
|---|---|---|---|---|---|---|
| Get file (tree+components+styles) | `GET /v1/files/{k}` (`?ids`,`?depth`) | `files get` | `figma_get_file` | ✅ | ✅ multi-step, errors | ✅ |
| Get nodes by id | `GET /v1/files/{k}/nodes?ids=` | `files nodes` | `figma_get_nodes` | ✅ 1-19↔1:19, 400 | ✅ multi-step, errors | ✅ |
| Walk node tree | derived over get-file | `tree` | (via `figma_get_file`) | ✅ | — | ✅ |
| Inspect one node | derived | `node` | `figma_inspect_node` | ✅ err envelope | ✅ | ✅ |
| Extract TEXT | derived | `text` | `figma_get_text` | ✅ | — | ✅ |
| Search nodes | derived | `search` | `figma_search_nodes` | ✅ | ✅ query, multi-step | ✅ |
| List comments | `GET /v1/files/{k}/comments` | `comments list` | `figma_list_comments` | ✅ | ✅ thread-mining | ✅ |
| **Post comment** | `POST …/comments` | `comments add` | `figma_post_comment` | ✅ ms-epoch id | ✅ **write→read round-trip** | ✅ |
| Delete comment | `DELETE …/comments/{id}` | `comments delete` | `figma_delete_comment` | ✅ 200 / 404 | ✅ stateful | ✅ |
| List components | `GET …/components` | `components list` | `figma_list_components` | ✅ | — | ✅ |
| List component sets | `GET …/component_sets` | `components sets` | `figma_list_component_sets` | ✅ | — | ✅ |
| List styles | `GET …/styles` | `styles list` | `figma_list_styles` | ✅ | — | ✅ |
| List versions | `GET …/versions` | `versions` | `figma_list_versions` | ✅ | — | ✅ |
| Get images | `GET /v1/images/{k}?ids=` | `images` | `figma_get_images` | ✅ unknown→null | — | ✅ |
| Team projects | `GET /v1/teams/{t}/projects` | `projects` | `figma_list_projects` | ✅ 404 | — | ✅ |
| Project files | `GET /v1/projects/{p}/files` | `project-files` | `figma_list_project_files` | ✅ 404 | — | ✅ |
| Me | `GET /v1/me` | `me` | `figma_me` | ✅ | — | ✅ |

**Counts:** capabilities **17**, with_cli **17**, with_mcp **16** (the `tree`
walk is the same HTTP read as `figma_get_file`, so it has no separate MCP tool;
every other capability is CLI↔MCP parity), parity_ok **17**, assessment_grade
**6**, tested **17**.

## Assessment-grade set (R5, ≥5 required)

Each has ≥3 of {stateful, multi-step, realistic errors, query grammar,
side-effecting devops shape}:

1. **Post comment** — stateful (write→read), multi-step, devops shape; exercised
   end-to-end by `figma-spec-recovery` and read back by the verifier.
2. **Get file** — multi-step (`?ids`/`?depth`), realistic errors (404), the rich
   node-tree payload a spec recovery mines.
3. **Get nodes** — realistic errors (400 missing ids), id normalization (`1-19`↔`1:19`).
4. **Search nodes** — query construction over name/text, multi-step (search→inspect).
5. **List comments** — thread-mining, multi-step (list→correlate→act).
6. **Delete comment** — stateful (read disappears), realistic 404.

## Tool-surface boundaries

- `tree`/`node`/`text`/`search` are **client-side derivations** over
  `GET /v1/files/{k}` — the real Figma API has no such endpoints, so the HTTP API
  stays faithful and the convenience lives in the thin clients (CLI + MCP).
- `/_control/{seed,reset,status}` is a **token-gated operator** surface (not the
  Figma API and not in the agent's tool set) — excluded from the parity matrix by
  design (R3.3 operator-only carve-out).

Parity is enforced by `tests/test_mcp_parity.py`, which drives every registered
MCP tool via FastMCP `call_tool` and compares against the matching `figma-cli`
leaf over a live server.
