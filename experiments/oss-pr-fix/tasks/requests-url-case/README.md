# requests-url-case

A multi-surface software-engineering task. Reviewer notes — the agent never
sees this file.

## a) Summary

A partner integration is failing because a vendored HTTP client matches URL
schemes case-sensitively, so `HTTP://` / `HTTPS://` URLs raise "No connection
adapters were found" and skip cert verification. This mirrors the real
psf/requests PR #1385. The agent is told only *"there's a task assigned to Sam —
go find it and fix it."* It must discover the bug, work out the team's agreed
fix, implement it in the right repo, and open a pull request. Reward is 1 only if
a PR's head passes both the existing tests and the hidden bug tests; otherwise 0.

## b) What data + tools the agent gets, and how it uses them

The instruction names **no** tools. Everything below is discovered by the agent
(the CLIs are on `PATH`, the MCP server is registered in `task.toml`). All seed
data lives *inside the services* — the agent cannot read it off disk, only
through the tools.

- **Issue tracker** — `linear` / `jira` CLIs (a Linear/Jira clone). Holds ~23
  tickets. `linear issue mine` lists the tickets assigned to Sam (the agent's
  identity). Used to find the work item and its comments.
- **Team chat** — `slack` CLI + `slack-mcp` MCP server. ~470 messages across 24
  channels. Holds the *exact* fix contract, split across `#eng` and
  `#web-platform`.
- **Code host** — `git` + `gh` against a self-hosted GitHub forge (Forgejo).
  Repos live under the `meridian` org. The agent clones the buggy repo, writes
  the fix, pushes a branch, and opens a PR against `main`.

## c) Required steps

1. Discover the tracker; `linear issue mine` → find **WEB-101** (p1, In
   Progress) among Sam's tickets.
2. Read it: the description gives the symptom; the **latest** comment names the
   repo (`meridian/webapp`) and points to team chat.
3. In Slack, read `#eng` to the current decision (an older thread is wrong), then
   follow it to **#web-platform** for the exact two-site contract.
4. Clone `meridian/webapp` (not the decoy repos).
5. Apply `.lower()` at the scheme comparison in **both** sites:
   `Session.get_adapter` in `requests/sessions.py` and `HTTPAdapter.cert_verify`
   in `requests/adapters.py`.
6. Open a PR against `main`.

## d) What was done to make it hard (noise / bait / traps)

- **Minimal prompt:** no tools, repo, or "open a PR" stated — the agent must
  self-orient.
- **Linear noise + decoy:** ~23 tickets; 7 assigned to Sam. A *second* p1
  ticket (WEB-108) lures a one-site-only fix ("just fix `get_adapter`").
- **Temporal bait:** an older (~3-week-old) Slack/Linear thread agrees on the
  wrong approach (`casefold` / lowercasing the whole URL); the recent thread
  overrides it.
- **Split contract:** the symptom-level guidance lives in `#eng`; the exact
  two-site `url.lower().startswith(...)` mechanics live in `#web-platform`.
- **Keyword poison:** a decoy channel plants `url.lower().startswith` in a
  foreign, negated context ("the edge-proxy moved to a regex").
- **Decoy repos:** `meridian/edge-proxy` and `meridian/dns-resolver` hold
  plausible scheme/casing code; a PR there scores 0.
- **In-repo misdirection:** a `CONTRIBUTING.md` says URL normalization is
  centralized in `utils.py` (wrong); a comment says casing is handled by the
  proxy layer (wrong).
- **Typos and ~470 messages** of unrelated chatter throughout.
- **Contract-strict tests:** fixing only one of the two sites, or mutating the
  adapter prefix map, passes a naive reading but fails the hidden tests.

Baselines: `nop` opens no PR → 0; `oracle` (`solution/solve.sh`) applies exactly
the fix above → 1.
