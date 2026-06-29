# ghc — gh CLI command parity & implementation plan

Goal: **drop-in parity with the `gh` commands actually used day-to-day**, backed
by a local Forgejo forge, runnable offline as a CLI *and* an MCP server. Esoteric
surface comes later.

## How the mapping works

`gh` talks to `api.github.com` (REST + GraphQL). `ghc` talks to **Forgejo's
REST API** (`/api/v1`, Gitea-compatible, Swagger at `/api/swagger`). There is no
GraphQL on Forgejo, so anything `gh` does via GraphQL we re-express as one or more
REST calls in `ForgejoClient`. The whole translation lives in **one place**
(`ghclone/forge/client.py`); the CLI and MCP are thin presentation layers over it.

Concept mapping:

| GitHub (gh) | Forgejo | Notes |
|---|---|---|
| `OWNER/REPO` | `OWNER/REPO` | identical |
| issue/PR number | `index` (per-repo) | identical 1-based index |
| `gh api` REST path | `/api/v1/...` path | path shapes differ; see `gh api` row |
| GraphQL queries | N REST calls | re-implemented per command |
| PAT scopes | Forgejo token scopes | `all` for the local fixture |
| Actions/workflows | Forgejo Actions (act_runner) | subset; P1 |
| Marketplace actions | vendored by URL | no marketplace; P1 |

Status legend: ✅ implemented & tested · 🔜 planned (next) · ⚠️ needs a shim/compromise · ❌ no Forgejo equivalent (stub/skip).

> **P0 is complete** — all `auth`/`repo`/`issue`/`pr` verbs below plus `gh api`
> are implemented in the CLI **and** MCP server, and verified live against a
> running Forgejo (see `tests/test_integration.py`). The 🔜 flags that remain on
> individual P0 rows are minor flag-completeness items, not missing commands.

---

## P0 — repos, issues, PRs (the daily drivers)

### `ghc auth`
| Command | Forgejo call | Status |
|---|---|---|
| `auth login` | `GET /user` (validate token) → store in `hosts.json` | ✅ |
| `auth status` | `GET /user` | ✅ |
| `auth logout` | remove host entry | 🔜 |
| `auth token` | print stored token | 🔜 |

### `ghc repo`
| Command | Forgejo call | Status |
|---|---|---|
| `repo list [owner]` | `GET /user/repos` / `GET /users/{o}/repos` / `GET /orgs/{o}/repos` | ✅ |
| `repo view OWNER/REPO` | `GET /repos/{o}/{r}` | ✅ |
| `repo create` | `POST /user/repos` or `POST /orgs/{o}/repos` | ✅ |
| `repo delete` | `DELETE /repos/{o}/{r}` | ✅ (client) |
| `repo clone` | shell out to `git clone <forge>/{o}/{r}.git` | 🔜 |
| `repo fork` | `POST /repos/{o}/{r}/forks` | 🔜 |
| `repo rename` | `PATCH /repos/{o}/{r}` `{name}` | 🔜 |
| `repo edit` (desc/visibility/topics) | `PATCH /repos/{o}/{r}` | 🔜 |
| `repo set-default` | client-side config | 🔜 |

### `ghc issue`
| Command | Forgejo call | Status |
|---|---|---|
| `issue list` | `GET /repos/{o}/{r}/issues?type=issues&state=` | ✅ |
| `issue view N` | `GET /repos/{o}/{r}/issues/{N}` | ✅ |
| `issue create` | `POST /repos/{o}/{r}/issues` | ✅ |
| `issue comment N` | `POST /repos/{o}/{r}/issues/{N}/comments` | ✅ |
| `issue close / reopen N` | `PATCH .../issues/{N}` `{state}` | 🔜 |
| `issue edit N` | `PATCH .../issues/{N}` (title/body/labels/assignees) | 🔜 |
| `issue list --label/--assignee/--author` | same endpoint, query params | 🔜 |
| `issue status` | filter `GET .../issues?assigned/created` | 🔜 |

> Forgejo treats issues and PRs as one `issues` collection (PRs are issues with a
> `pull_request` field). We pass `type=issues` / `type=pulls` to disambiguate.

### `ghc pr`
| Command | Forgejo call | Status |
|---|---|---|
| `pr list` | `GET /repos/{o}/{r}/pulls?state=` | ✅ |
| `pr view N` | `GET /repos/{o}/{r}/pulls/{N}` | ✅ (client) |
| `pr create` | `POST /repos/{o}/{r}/pulls` `{title,head,base,body}` | ✅ |
| `pr merge N` | `POST .../pulls/{N}/merge` `{Do: merge\|rebase\|squash}` | ✅ |
| `pr checkout N` | resolve head ref → `git fetch`/`checkout` | 🔜 |
| `pr diff N` | `GET .../pulls/{N}.diff` | 🔜 |
| `pr close / reopen N` | `PATCH .../issues/{N}` `{state}` | 🔜 |
| `pr edit N` | `PATCH .../pulls/{N}` | 🔜 |
| `pr ready / draft` | `PATCH .../pulls/{N}` `{...}` | ⚠️ verify draft field support |
| `pr status` | composite (created/assigned/review-requested) | 🔜 |
| `pr comment N` | `POST .../issues/{N}/comments` | 🔜 |

### `ghc api` (escape hatch — high value, do early)
| Command | Implementation | Status |
|---|---|---|
| `api <path>` | pass-through to `/api/v1/<path>` with method/fields/`--paginate` | 🔜 |
| `api graphql` | ❌ no GraphQL on Forgejo → error with a clear message + suggest REST | ⚠️ |

`gh api` is how power users/scripts reach anything not wrapped. Implement REST
pass-through with `-X`, `-f/-F` fields, `--paginate`, `--jq`. GraphQL is the one
hard gap — return a descriptive error.

---

## P1 — Actions/Workflows, code review, comments, artifacts, auth, metadata

### `ghc run` / `ghc workflow` (Actions)
| Command | Forgejo call | Status |
|---|---|---|
| `workflow list` | `GET /repos/{o}/{r}/actions/workflows` | 🔜 |
| `run list` | `GET /repos/{o}/{r}/actions/tasks` (runs) | 🔜 |
| `run view [--log]` | run detail + `GET .../logs` | ⚠️ log endpoint shape differs |
| `run watch` | poll run status | 🔜 |
| `workflow run` (dispatch) | `POST .../actions/workflows/{wf}/dispatches` | ⚠️ verify dispatch support |
| `run rerun / cancel` | `POST .../tasks/{id}/rerun|cancel` | ⚠️ |

> Needs the `act_runner` service (compose, commented in). Forgejo Actions is a GH
> Actions *subset*: no Marketplace (reference actions by full URL), `GITHUB_*`→`FORGEJO_*`.

### `ghc pr review` (code review)
| Command | Forgejo call | Status |
|---|---|---|
| `pr review --approve/--request-changes/--comment` | `POST .../pulls/{N}/reviews` | 🔜 |
| `pr review` (list) | `GET .../pulls/{N}/reviews` | 🔜 |
| line/thread comments | `POST .../pulls/{N}/reviews` with `comments[]` (path/line) | ⚠️ REST thread model ≠ GH GraphQL |

### comments / metadata
| Command | Forgejo call | Status |
|---|---|---|
| `issue/pr comment` (edit/list) | `GET/PATCH .../issues/comments/{id}` | 🔜 |
| reactions | `POST .../issues/{N}/reactions` | 🔜 |
| `label list/create/edit/delete` | `/repos/{o}/{r}/labels` | 🔜 |
| `gh repo view` topics/metadata | `/repos/{o}/{r}/topics` | 🔜 |
| milestones | `/repos/{o}/{r}/milestones` | 🔜 |

### artifacts
| Command | Forgejo call | Status |
|---|---|---|
| `run download` (artifacts) | `GET .../actions/artifacts` + download | ⚠️ artifacts supported; `actions/cache` is runner-local (differs from GH) |

### auth / metadata (P1 depth)
| Command | Forgejo call | Status |
|---|---|---|
| `auth refresh` / scopes | token scope mgmt `/users/{u}/tokens` | 🔜 |
| `api /user`, `/orgs`, `/repos` metadata | direct REST | 🔜 |
| SSH key mgmt (`gh ssh-key`) | `/user/keys` | 🔜 |

---

## Known cross-cutting gaps (decide handling)
- **GraphQL** — none on Forgejo. `gh api graphql` and any GraphQL-only `gh`
  feature must be re-expressed as REST or stubbed.
- **Marketplace actions** — vendor by full URL in workflows.
- **Projects v2 / Discussions / Pages** — no native equivalent; out of scope unless tasks need them.
- **`actions/cache`** — runner-local on Forgejo, not server-hosted.

## Build order
1. ✅ Scaffold: client + auth/repo/issue/pr happy paths (CLI + MCP).
2. ✅ P0 verbs (close/reopen/edit/clone/checkout/diff/review) + `gh api` REST pass-through.
3. ✅ `--json` output + exit-code parity for scripting (`--jq` TODO).
4. ✅ Hydration: Engine A (`repo migrate`) + Engine B (`hydrate snapshot/apply/verify`).
   See [HYDRATION.md](HYDRATION.md). Replay validated offline against live Forgejo
   (number preservation, author remap via Sudo, ghost provenance, PR fallback).
5. ✅ P1 metadata: label CRUD, milestone CRUD, reactions (CLI `label`/`milestone`/`issue react` + MCP).
6. ✅ P1 Actions: `workflow list/run` (dispatch), `run list` (tasks). Listing works against
   the API; **actual run execution needs a registered `act_runner`** (compose service,
   commented in — enable + register with `ghc api repos/{o}/{r}/actions/runners/registration-token`).
   ⚠️ **Artifacts**: Forgejo exposes no `/actions/artifacts` v1 REST endpoint — not wrappable
   via REST yet (download is UI/internal-API only). Tracked as a known gap.
7. 🔜 `--jq` filtering; Dockerfile for ghc + an MCP image so the whole thing ships offline.
