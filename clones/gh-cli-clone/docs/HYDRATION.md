# Hydration plan — GitHub repo → ghc (Forgejo) repo

Turn a real GitHub repo into a local ghc/Forgejo repo: **git history + issues +
PRs + comments + labels + milestones + releases**, with author identity remapped,
runnable offline afterward, and reproducible from a cached snapshot.

This is the "Data Hydration" workstream for Worlds: the output is a faithful,
offline clone of a real repo that an agent can operate on via `ghc`/MCP — and the
snapshot layer is where APEX-style synthetic incident data later gets injected.

## Two engines (use both)

### Engine A — Forgejo native migrate (fast path, P0)
Forgejo ships a GitHub downloader. One API call pulls almost everything:

`POST /api/v1/repos/migrate`
```jsonc
{
  "clone_addr": "https://github.com/OWNER/REPO.git",
  "service": "github",
  "auth_token": "<github PAT>",      // read-only; only needed at hydrate time
  "repo_name": "REPO", "repo_owner": "ghc-admin",
  "mirror": false,
  "issues": true, "pull_requests": true, "labels": true,
  "milestones": true, "releases": true, "wiki": true
}
```
Handles: git (all branches/tags/history), issues + comments, PRs (incl.
`refs/pull/N/head` reconstruction), labels, milestones, releases, wiki.
**Preserves issue/PR numbers.** Unmapped GitHub authors become a placeholder
("ghost") with the original handle kept in the body.

Exposed as `ghc-hydrate migrate <github-url> [--into OWNER/REPO]`.

**Limits:** needs network to GitHub + a PAT *at hydrate time* (the result is
offline); author remap is coarse; you can't inject synthetic data; not
reproducible from a frozen artifact. That's why we also build Engine B.

### Engine B — snapshot + replay (controlled path, P1)
Two stages so the *pull* (needs GitHub) and the *load* (offline) are separable —
this gives reproducibility, anonymization, and an injection point for synthetic data.

**Stage 1 — `ghc-hydrate snapshot OWNER/REPO --out <dir>`** (needs GitHub, run once)
Pull via GitHub REST and freeze to disk:
```
snapshot/
  repo.json                 # metadata: description, topics, default_branch, created_at
  git.bundle                # `git clone --mirror` → `git bundle create` (all refs+history)
  issues/NNNN.json          # issue + comments + labels + events + reactions
  pulls/NNNN.json           # PR + review comments + reviews + commits + diff + base/head sha
  labels.json  milestones.json  releases.json
  users.map.json            # github_login -> {ghc_login, strategy}   (editable before apply)
  MANIFEST.json             # counts, source commit, snapshot time, tool version
```
This artifact is **committable as a fixture** → reproducible hydration, diffable,
and the place to layer synthetic incidents later.

**Stage 2 — `ghc-hydrate apply <dir> --into OWNER/REPO`** (offline, idempotent)
Replay the snapshot into Forgejo via `ForgejoClient` + git:
1. `repo create` (metadata, topics, default branch).
2. Push git: `git clone git.bundle` → `git push --mirror <forge>/OWNER/REPO.git`
   (lands all branches/tags/history, including `refs/pull/N/head`).
3. Labels → milestones → (in number order) issues → PRs, so indices line up.
4. For each issue/PR: create, then replay comments in timestamp order.
5. Apply final state (closed/merged) last.

## Hard problems & how we handle them

| Problem | Handling |
|---|---|
| **Issue/PR number preservation** | Import in original numeric order; create placeholders for gaps (deleted items) so indices stay aligned, then close them. Forgejo shares one index across issues+PRs, like GitHub. |
| **Author identity** | `users.map.json`: known GitHub logins → pre-created Forgejo users; unknown → `ghost`. Always prepend `> _originally by @login on DATE_` to body/comment so provenance survives even when attribution can't. |
| **PR head/base branches** | Snapshot records base+head SHAs and pushes `refs/pull/N/head` from the bundle. Open PRs with live branches recreate cleanly; merged/closed PRs use the synthetic pull ref so the diff is viewable even if the source branch is gone. |
| **Merged/closed PRs** | Create the PR from the pull ref, replay reviews/comments, then set merged/closed state. If the head ref truly can't be reconstructed, fall back to a closed issue labeled `migrated-pr` with the diff attached (logged, never silent). |
| **Timestamps** | Forgejo migrate preserves original `created_at`; in Engine B we set `created`/`updated` via the API where allowed, else note drift in MANIFEST. |
| **Rate limits / large repos** | Snapshot stage paginates + checkpoints (resume from last fetched number); honors GitHub rate-limit headers. |
| **Reactions / review threads** | Best-effort: reactions via `/reactions`; line-level review comments via `POST /pulls/{n}/reviews` with `comments[]{path,line}`. REST thread model ≠ GitHub GraphQL, so threading is approximate — logged. |
| **Secrets in history** | Optional `--scrub` pass over snapshot before apply. |

## Offline / reproducibility story
- Engine B's snapshot is the **offline artifact**: once captured, `apply` needs
  only the local Forgejo. Commit snapshots as fixtures for repeatable worlds.
- Engine A is the quick one-shot when you just need a live clone and have a PAT.

## Verification (every hydration emits a report)
- counts: issues/PRs/comments/labels/releases (source vs landed) — flag any drop.
- `nop`-style check: random sample of N issues/PRs diffed source↔Forgejo (title, body, state, comment count, author-or-ghost).
- git parity: `git rev-list --count --all` and tag/branch set match.
- exit non-zero if any category drops >0 silently.

## Build order
1. `ghc-hydrate migrate` (Engine A wrapper over `POST /repos/migrate`) — fastest value.
2. `ghc-hydrate snapshot` (GitHub REST → frozen artifact, with users.map.json).
3. `ghc-hydrate apply` (offline replay: git push + issues/PRs/comments in order).
4. Hydration report + sample-diff verifier.
5. Hook: synthetic-incident injection into a snapshot (ties to APEX/Worlds).

## Operator surface (NOT agent-facing)
Hydration is a **world-building** step run by the task author / harness, so it
lives in a separate `ghc-hydrate` entrypoint — it is deliberately **not** in the
agent's `ghc` CLI or the agent MCP server. The harness hydrates the world, then
hands the agent the gh-parity surface only.
```
ghc-hydrate migrate <github-url> [--into OWNER/REPO] [--mirror]
ghc-hydrate snapshot OWNER/REPO --out DIR [--token $GH_TOKEN] [--resume]
ghc-hydrate apply DIR --into OWNER/REPO [--users users.map.json] [--as-of <sha|ts>] [--dry-run]
ghc-hydrate verify DIR --against OWNER/REPO
```
