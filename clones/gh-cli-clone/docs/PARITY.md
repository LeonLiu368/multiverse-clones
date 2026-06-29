# ghc — full feature list, command list & `gh` parity

`ghc` is a `gh`-compatible CLI + MCP server over a self-hosted **Forgejo** forge,
runnable offline. This is the authoritative list of **what it does** and **how it
maps to `gh`**.

Every agent-facing command below is exercised end-to-end through the `gh` shim
against a live forge by `scripts/agent-coverage.sh` — **41/41 passing**
(`tests/test_coverage_live.py`). A real model (gemini-3.5-flash via Harbor) drives
the surface too: 3/3 on tasks spanning P0+P1 (see [HARBOR.md](HARBOR.md)).

Legend: ✅ parity · 🟡 parity with a documented difference · ⚙️ operator-only
(not agent-facing) · ❌ no Forgejo equivalent.

---

## Features

| Feature | Status |
|---|---|
| gh-compatible CLI (`ghc`, drop-in via `gh` shim) | ✅ |
| MCP server (`ghc-mcp`) exposing the same operations as tools | ✅ |
| Offline: Forgejo in Docker, SQLite, no SaaS | ✅ |
| Single REST translation layer (`ForgejoClient`) for CLI + MCP + hydration | ✅ |
| Multi-host config (gh-style `hosts.json`) + token auth | ✅ |
| `--json` output for scripting | ✅ |
| Hydration: GitHub repo → forge (native migrate + snapshot/replay) | ⚙️ |
| Point-in-time hydration (`--as-of` commit/timestamp) | ⚙️ |
| Agent/operator boundary (hydration not reachable by the agent) | ✅ |
| GraphQL | ❌ (REST-only forge) |
| Actions execution / artifacts download | 🟡 / ❌ (see gaps) |

---

## P0 — repos, issues, PRs

### auth
| ghc | gh equivalent | parity |
|---|---|---|
| `ghc auth login --host H [--token T]` | `gh auth login` | ✅ |
| `ghc auth status` | `gh auth status` | ✅ |
| `ghc auth token` | `gh auth token` | ✅ |
| `ghc auth logout --host H` | `gh auth logout` | ✅ |

### repo
| ghc | gh equivalent | parity |
|---|---|---|
| `ghc repo list [owner] [--json]` | `gh repo list` | ✅ |
| `ghc repo view OWNER/REPO [--json]` | `gh repo view` | ✅ |
| `ghc repo create NAME [--private] [-d] [--org]` | `gh repo create` | ✅ |
| `ghc repo delete OWNER/REPO [--yes]` | `gh repo delete` | ✅ |
| `ghc repo clone OWNER/REPO [DEST]` | `gh repo clone` | ✅ |
| `ghc repo fork OWNER/REPO [--org]` | `gh repo fork` | ✅ |
| `ghc repo rename OWNER/REPO NEW` | `gh repo rename` | ✅ |
| `ghc repo edit OWNER/REPO [-d] [--private/--public] [--topics]` | `gh repo edit` | ✅ |

### issue
| ghc | gh equivalent | parity |
|---|---|---|
| `ghc issue list -R [--state] [--label] [--milestone] [--search] [--json]` | `gh issue list` | ✅ |
| `ghc issue view N -R [--comments] [--json]` | `gh issue view` | ✅ |
| `ghc issue create -R -t -b` | `gh issue create` | ✅ |
| `ghc issue comment N -R -b` | `gh issue comment` | ✅ |
| `ghc issue edit N -R [-t] [-b]` | `gh issue edit` | ✅ |
| `ghc issue close N -R` | `gh issue close` | ✅ |
| `ghc issue reopen N -R` | `gh issue reopen` | ✅ |
| `ghc issue react N -R -c <emoji>` | (gh: via API) | 🟡 first-class here |

### pr
| ghc | gh equivalent | parity |
|---|---|---|
| `ghc pr list -R [--state] [--json]` | `gh pr list` | ✅ |
| `ghc pr view N -R [--json]` | `gh pr view` | ✅ |
| `ghc pr create -R -t -H -B -b` | `gh pr create` | ✅ |
| `ghc pr diff N -R` | `gh pr diff` | ✅ |
| `ghc pr checkout N -R` | `gh pr checkout` | ✅ |
| `ghc pr merge N -R [--method merge\|rebase\|rebase-merge\|squash]` | `gh pr merge` | ✅ |
| `ghc pr close N -R` | `gh pr close` | ✅ |
| `ghc pr reopen N -R` | `gh pr reopen` | ✅ |
| `ghc pr review N -R [--approve\|--request-changes\|--comment] [-b]` | `gh pr review` | ✅ |

### api (escape hatch)
| ghc | gh equivalent | parity |
|---|---|---|
| `ghc api PATH [-X M] [-f k=v] [--paginate]` | `gh api` (REST) | 🟡 REST only |
| `ghc api graphql` | `gh api graphql` | ❌ errors by design (no GraphQL on Forgejo) |

---

## P1 — Actions, code review, comments, metadata

### label
| ghc | gh equivalent | parity |
|---|---|---|
| `ghc label list -R [--json]` | `gh label list` | ✅ |
| `ghc label create -R -n [-c] [-d]` | `gh label create` | ✅ |
| `ghc label delete ID -R` | `gh label delete` | 🟡 by id (Forgejo) vs name |

### milestone
| ghc | gh equivalent | parity |
|---|---|---|
| `ghc milestone list -R [--state] [--json]` | (gh: via API) | 🟡 first-class here |
| `ghc milestone create -R -t [-d]` | (gh: via API) | 🟡 first-class here |

### workflow / run (Actions)
| ghc | gh equivalent | parity |
|---|---|---|
| `ghc workflow list -R [--json]` | `gh workflow list` | 🟡 reads repo files (no list API) |
| `ghc workflow run NAME -R [--ref]` | `gh workflow run` | ✅ dispatch |
| `ghc run list -R [--json]` | `gh run list` | 🟡 Forgejo "tasks" |
| `ghc run artifacts [RUN] -R [--json]` | (gh: `gh run view`) | 🟡 first-class here |
| `ghc run download [RUN] -R [-n] [-D]` | `gh run download` | 🟡 via Forgejo web route |

**Execution + artifacts verified:** with a runner (`scripts/start-runner.sh`), a
pushed workflow ran to `success`, uploaded an artifact (`upload-artifact@v3`), and
`ghc run download` fetched + extracted it (`result.txt` round-tripped). `gh run
download` is implemented over Forgejo's web artifact route (`/{o}/{r}/actions/runs/
{run_number}/artifacts/{name}`, token-auth) since there's no `/api/v1` endpoint.

### code review / comments
Covered by `pr review` (approve/request-changes/comment) and `issue comment` /
`issue react` above. PR review **list** + per-comment edit/delete exist on
`ForgejoClient` (`list_reviews`, `edit_comment`, `delete_comment`) — not yet
surfaced as dedicated CLI verbs.

---

## Operator-only (⚙️ NOT agent-facing) — `ghc-hydrate`
| Command | Purpose |
|---|---|
| `ghc-hydrate migrate <github-url> [--into] [--mirror]` | Engine A: native one-call migrate |
| `ghc-hydrate snapshot OWNER/REPO --out DIR` | Engine B stage 1: freeze GitHub → artifact |
| `ghc-hydrate apply DIR --into o/r [--as-of <sha\|ts>] [--users] [--dry-run]` | Engine B stage 2: offline replay (point-in-time) |
| `ghc-hydrate verify DIR --against o/r` | count + sample-diff report |

Deliberately a separate entrypoint so the agent under test can't reach
world-building tools. See [HYDRATION.md](HYDRATION.md).

---

## Where ghc differs from real `gh` (the honest gaps)
1. **No GraphQL.** Forgejo is REST-only. `gh api graphql` and any GraphQL-only gh
   behavior are re-expressed as REST or rejected. The biggest structural difference.
2. **Artifacts.** No `/api/v1` endpoint, but **`gh run download` IS implemented**
   over Forgejo's web artifact route (token-auth) — verified round-trip. The v4
   artifact actions (`upload/download-artifact@v4`) refuse non-github.com hosts
   (GHES guard), so workflows must use **`@v3`**.
3. **Actions execution — SUPPORTED (with a runner).** Workflows actually run:
   register a runner with `scripts/start-runner.sh`, push a `.forgejo/workflows/*.yml`
   (`runs-on: docker`), and it executes — **verified end-to-end** (push → run goes
   running → `success`). It's a GitHub Actions *subset*: **no Marketplace** (actions
   referenced by full URL), `.github/` or `.forgejo/workflows`, `GITHUB_*`→`FORGEJO_*`
   (github aliases provided). Without a runner registered, dispatch/list still work
   but jobs stay queued.
4. **`gh api --jq`** filtering not implemented (pipe to `jq`).
5. **Label by id, not name** for delete/assoc (Forgejo's label API is id-based).
6. **No Projects v2 / Discussions / Pages** (no Forgejo equivalent).

Everything outside these gaps is at parity and verified — 41/41 commands through
the agent interface, plus real-model (gemini) task validation.
