# requests-json-nan

A multi-surface software-engineering task. Reviewer notes — the agent never
sees this file.

## a) Summary

Production is throwing 400s because a vendored HTTP client serializes
`float('nan')`/`float('inf')` straight into JSON request bodies (invalid JSON
that the gateway rejects). This mirrors the real psf/requests PR #5810. The
agent is told only *"there's a task assigned to Sam — go find it and fix it."*
It must discover the bug, work out the team's agreed fix, implement it in the
right repo, and open a pull request. Reward is 1 only if a PR's head passes both
the existing tests and the hidden bug tests; otherwise 0.

## b) What data + tools the agent gets, and how it uses them

The instruction names **no** tools. Everything below is discovered by the agent
(the CLIs are on `PATH`, the MCP server is registered in `task.toml`). All seed
data lives *inside the services* — the agent cannot read it off disk, only
through the tools.

- **Issue tracker** — `linear` / `jira` CLIs (a Linear/Jira clone). Holds ~23
  tickets. `linear issue mine` lists the tickets assigned to Sam (the agent's
  identity). Used to find the work item and its comments.
- **Team chat** — `slack` CLI + `slack-mcp` MCP server. ~470 messages across 24
  channels. Holds the *exact* fix contract, split across `#eng` and `#api-team`.
- **Code host** — `git` + `gh` against a self-hosted GitHub forge (Forgejo).
  Repos live under the `meridian` org. The agent clones the buggy repo, writes
  the fix, pushes a branch, and opens a PR against `main`.

## c) Required steps

1. Discover the tracker; `linear issue mine` → find **API-202** (p1, In
   Progress) among Sam's tickets.
2. Read it: the description gives the symptom; the **latest** comment names the
   repo (`meridian/api-service`) and points to team chat.
3. In Slack, read `#eng` to the current decision (an older thread is wrong), then
   follow it to **#api-team** for the exact contract.
4. Clone `meridian/api-service` (not the decoy repos).
5. Add `InvalidJSONError(RequestException)` to `requests/exceptions.py`; in
   `requests/models.py` pass `allow_nan=False` to `json.dumps` and re-raise the
   `ValueError` as `InvalidJSONError(ve, request=self)`.
6. Open a PR against `main`.

## d) What was done to make it hard (noise / bait / traps)

- **Minimal prompt:** no tools, repo, or "open a PR" stated — the agent must
  self-orient.
- **Linear noise + decoy:** ~23 tickets; 7 assigned to Sam. A *second* p1
  ticket (API-215) confidently proposes the wrong approach (`JSONDecodeError`).
- **Temporal bait:** an older (~3-week-old) Slack/Linear thread agrees on the
  wrong `JSONDecodeError` plan; the recent thread overrides it.
- **Split contract:** the exception name lives in `#eng`; the exact
  `allow_nan=False` / `request=self` mechanics live in `#api-team`.
- **Keyword poison:** a decoy channel plants `InvalidJSONError` in a foreign,
  negated context ("renamed in the analytics SDK").
- **Decoy repos:** `meridian/metrics-exporter` and `meridian/gateway-service`
  hold plausible NaN-handling code; a PR there scores 0.
- **In-repo misdirection:** a `CONTRIBUTING.md` says new exceptions go in
  `errors.py` (wrong); a comment says NaN handling is done upstream (wrong).
- **Typos and ~470 messages** of unrelated chatter throughout.
- **Contract-strict tests:** a substring NaN check, or dropping `request=self`,
  passes a naive reading but fails the hidden tests.

Baselines: `nop` opens no PR → 0; `oracle` (`solution/solve.sh`) applies exactly
the fix above → 1.
