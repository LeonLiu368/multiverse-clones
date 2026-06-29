# Substituting `ghc` for `gh` in a task (acceptance)

Goal: drop our Forgejo-backed clone into an APEX/SWE task in place of `gh`, and
confirm an agent has **every tool it needs** to do a real "fix the bug" loop —
fully offline.

## The shim
`scripts/gh` is a drop-in `gh` that forwards to `ghc`. Put it first on `PATH`
inside the task sandbox and anything that calls `gh ...` hits the offline forge:

```bash
export PATH="/path/to/gh-cli-clone/scripts:$PATH"   # `gh` is now the shim
export GHC_HOST=http://localhost:3300
export GHC_TOKEN=$(cat /path/to/gh-cli-clone/ghc-token.txt)
gh auth status        # -> ghc -> Forgejo
```

Because `ghc`'s command tree and flags mirror `gh` (auth/repo/issue/pr/label/
milestone/run/workflow/api), the shim is a straight passthrough.

## Wiring into an APEX/harbor task
In the task's environment setup (Dockerfile / compose / `stage_data.sh`):
1. Run a Forgejo service (see `docker/docker-compose.yml`) and bootstrap a token.
2. **Hydrate** the task's source repo into it — at the incident moment:
   `ghc-hydrate apply <snapshot> --into <owner>/<repo> --as-of <base-commit>`
   (or `ghc-hydrate migrate <github-url>` for the quick path). `--as-of` gives the
   agent the repo **and its issue tracker** as they were before the fix.
3. Prepend `scripts/` to `PATH` and export `GHC_HOST`/`GHC_TOKEN`.
4. The agent's `gh` calls now operate on the offline world. No github.com.

This replaces APEX's reliance on a live forge / MCP-only issue discovery with a
real `gh` surface over a self-hosted, hydrated, point-in-time world.

## Verified capability checklist
`scripts/acceptance.sh` runs the whole loop via the shim and asserts each step
(green run committed in CI history):

- auth: `gh auth status`
- repo: `create`, `view`, `clone`
- issue: `create`, `list`, `view`, `close`, `react`
- git: push a fix branch over the token-authed remote
- pr: `create`, `view`, `diff`, comment, `review --approve`, `merge`
- metadata: `label create`
- escape hatch: `gh api repos/{o}/{r}`

Run it:
```bash
GHC_HOST=http://localhost:3300 GHC_TOKEN=$(cat ghc-token.txt) bash scripts/acceptance.sh
```

## Honest gaps (don't block the fix-the-bug loop)
- **Artifacts**: no Forgejo v1 REST endpoint — `gh run download` not wrappable yet.
- **Actions execution**: `workflow run`/`run list` work via API; *running* a
  workflow needs a registered `act_runner` (compose service, commented in).
- **`gh api --jq`**: not implemented (pipe to `jq`).
- **GraphQL**: unsupported by Forgejo; `gh api graphql` errors by design.
