# Multiverse clones — collected

Everything I built for the Multiverse service-clone work at Abundant AI (June–July 2026),
gathered from the original repositories into one place with **full commit history**.

The original repos lived under `github.com/abundant-ai/` and are no longer reachable from my
account. This collection was assembled on 2026-09-29 from my local clones, which turned out to
be *more* complete than GitHub was: several branches had commits that were never pushed.

**This is the public copy.** Real data that was used during development (a company's Jira and
Slack exports, Abundant's production telemetry, and my own Google data) was removed from every
commit before it was made public. See [Removed data](#removed-data) below.

## Layout

| Path | What it is | Original repo |
|---|---|---|
| `/` (root) | The clone monorepo: all clones in `clones/`, the creator and auditor skills in `skills/`, fleet-smoke in `experiments/`, `live/`, `viz/` | `abundant-ai/multiverse-clones` |
| `spoink/` | Snapshot engine: capture Slack/Linear/GitHub/Logfire, `slice_as_of(T)`, gateway bakes, task creator | `abundant-ai/spoink` |
| `seed-dashboard/` | Product-fidelity viewers for seeded clone data, overlay editor, patch export | `abundant-ai/seed-dashboard` |
| `abundant-identity/` | Cross-clone identity registry (local-only; never had a remote) | — |
| `origins/abundant-slack-clone/` | Standalone Slack clone, before it moved into the monorepo | `abundant-ai/abundant-slack-clone` |
| `origins/abundant-jira-clone/` | Standalone Jira/Linear clone | `abundant-ai/abundant-jira-clone` |
| `origins/abundant-logfire-clone/` | Standalone Logfire clone | `abundant-ai/abundant-logfire-clone` |
| `origins/figma-clone/` | Standalone Figma clone | `abundant-ai/figma-clone` |
| `origins/google-workspace-clone/` | Standalone Google Workspace clone | `abundant-ai/google-workspace-clone` |

**Why `origins/` duplicates code that's also in `clones/`.** On 2026-06-29 the monorepo started
by copying each clone's source in a single commit, which dropped the per-clone development
history. It also didn't copy everything: task environments, Dockerfiles, `slackgw/`, and whole
alternate implementations on side branches were left behind. `origins/` keeps those repos
intact. `clones/` is the later, canonical version; `origins/` is where it came from.

## History

Every commit from the repositories in the table below is here, with its original author, date
and message, except two that did nothing but add the removed Google Workspace tasks. Branches that never contained the removed data keep their **original hashes**; the
rest were rewritten to strip it, so their commits from that point on have new hashes. The table
shows both tips. (The task folders in `experiments/` were carried over differently; see the
next section.)

- `main` holds the root monorepo history plus each project, attached by a subtree merge.
- `archive/<repo>/<branch>` holds every original branch, minus the removed data.
- `wip/abundant-slack-clone/slack-focused-implementation` is that branch plus a snapshot of
  uncommitted work found in the local checkout.

To see a project's pre-import history, read its archive branch. `git log -- spoink/` only shows
commits made after the import, because the original commits touched root-level paths.

```bash
git log --oneline archive/spoink/main
git log --oneline archive/abundant-slack-clone/slack-mcp-oss
```

| Original repo | Branch | Commits | Original tip | Tip here | Notes |
|---|---|---|---|---|---|
| multiverse-clones | `main` | 75 | `d5aec88d9` | `f3c081cbb` | root mainline |
| multiverse-clones | `leon/fleet-smoke` | 16 | `a66dbd130` | `ece759182` | 1 commit never pushed |
| multiverse-clones | `leon/mv-image-naming` | 17 | `77d206c09` | `7cf44ab0c` | merged into main |
| spoink | `main` | 59 | `6edc9837b` | same |  |
| seed-dashboard | `main` | 33 | `a0f6caffa` | same |  |
| abundant-identity | `main` | 1 | `0ccad93df` | same | never had a remote |
| abundant-slack-clone | `slack-mcp-oss` | 40 | `bae979766` | `44ff87844` | imported to `origins/`; 2 commits never pushed; contains `main` + `prebuilt-image-refactor` |
| abundant-slack-clone | `main` | 19 | `c680b1f31` | `0499bb653` | behind GitHub's main, which had merged `slack-mcp-oss` |
| abundant-slack-clone | `prebuilt-image-refactor` | 16 | `de98bb1ac` | `4d7ea74a9` | never pushed |
| abundant-slack-clone | `mattermost-focused-implementation` | 11 | `62c2b0bcf` | same | prototype; 4 commits never pushed |
| abundant-slack-clone | `slack-focused-implementation` | 5 | `62a17e36e` | same | prototype; 1 commit never pushed |
| abundant-jira-clone | `main` | 8 | `17cf91d45` | `6523b7046` | 5 commits never pushed |
| abundant-jira-clone | `linear-graphql-surface` | 7 | `eabd19d81` | `06c1e96a9` | diverges from main |
| abundant-logfire-clone | `main` | 3 | `043b980f8` | same |  |
| figma-clone | `main` | 6 | `3f54f708a` | same |  |
| google-workspace-clone | `main` | 9 (7 here) | `8b3d3427d` | `a71c53a2e` | 7 commits never pushed; 2 commits that only added the removed tasks are gone |

Uncommitted edits found in the multiverse-clones and figma-clone checkouts are the two
`Snapshot uncommitted local changes` commits on `main`.

## Task folders from `abundant-ai/experiments`

`experiments/` also holds 22 task families I built on the clones. They came from the shared
`abundant-ai/experiments` repo, which also holds everyone else's work, so its history couldn't be
copied whole. Instead, only the commits that touched these folders were carried over, from the
branch holding each folder's newest version:

- Each commit keeps its original author, date and message, and has a new hash.
- Each one ends with an `Imported-from: abundant-ai/experiments@<hash> (<branch>)` line naming the
  original commit, so it can be traced back.
- Every folder was checked to be byte-identical to its source branch.

| Folder | Source branch | Commits | Notes |
|---|---|---|---|
| `action-bench-sample` | `leon/action-bench` | 5 | includes its earlier life as `action-bench-sample-1` |
| `apex-swe-clones` | `fix/loki-converter-multiline-fold` | 20 | + snapshot of uncommitted work (new task `paperless-ngx-10555-lb`, `tools/pr_to_task.py`) |
| `chat-tickets-observability` | `leon/chat-tickets-observability` | 5 | |
| `ethereum-clones` | `leon/ethereum-clones` | 1 | vendors the `op-geth` source (~88 MB) |
| `figma-ios` | `leon/figma-ios` | 1 | |
| `figma-linear` | `leon/figma-linear-handoff` | 3 | |
| `figma-observability` | `leon/figma-observability` | 1 | |
| `figma-realsim` | `origin/leon/figma-realsim` | 4 | the pushed branch was 3 commits ahead of the local one |
| `gauge-smoke` | `leon/gauge-smoke` | 4 | |
| `gh-ops-scenarios` | `leon/gh-ops-scenarios` | 4 | |
| `jira-smoke` | `leon/jira-smoke` | 1 | |
| `multi-clone-fetch` | `leon/multi-clone-fetch` | 5 | |
| `notion-smoke` | `leon/notion-smoke` | 1 | |
| `oss-pr-fix` | `leon/oss-pr-fix` | 13 | |
| `paperless-clones` | `paperless-clones` | 6 | includes its earlier life as `apex-paperless-poc`; + snapshot of a stash saved for this branch |
| `paperless-clones-datefix-internetblock` | `paperless-clones-datefix-internetblock` | 4 | |
| `slack-observability` | `leon/slack-observability` | 1 | |
| `slack-prod-overlay` | `leon/slack-prod-overlay` | 6 | |
| `slack-read` | `leon/slack-read` | 6 | |
| `slack-recent-lookup` | `leon/slack-recent-lookup` | 3 | |
| `taskfarm-clones` | `leon/taskfarm-clones` | 6 | |
| `three-surface-ops` | `leon/three-surface-ops` | 7 | |

## Removed data

These were removed from every commit on every branch before this copy was made public. A
`DATA-REMOVED.md` note sits wherever a folder lost its data.

| What | Where it was | Why |
|---|---|---|
| Jira production corpus | `**/selfcontained/base/data/eng-prod-state.json` | a real company's issue tracker, with personal contact details |
| 2021 Slack export | `**/seeds/eng-2021q1/`, `**/rw-large-slack-read/environment/data/` | a real company's internal conversations |
| Logfire production corpus | `**/abundant-logfire-clone/corpus/`, `**/logfire-incident-rca/environment/corpus/` | Abundant's production telemetry and internal endpoints |
| Google Workspace tasks `gws-event-room`, `gws-real-projects` | whole task folders and their sweep files | built on my own Gmail, Calendar and Drive; the tests also encode personal details |

Verified afterwards: none of the 77 file versions involved remain in the repository, no commit
touches those paths, and a scan of every data file in every commit finds no personal email
addresses or phone numbers. What remains is synthetic or small test data.

## Not included

- **`gauge`, `ticketvector`, `gh-cli-clone`**: mostly or entirely other people's work (several
  colleagues). The monorepo already carries a snapshot of each in `clones/`.
- **From `abundant-ai/experiments`:**
  - `oddish-incident`: its task ships Abundant's private `oddish` codebase, with full history, as a git bundle.
  - `apex-swe-variants`: shared with a colleague, and it runs on APEX's own Plane/Mattermost/Loki rather than the clones.
  - `saleor-spine-v1`, `stage3-5`, `stage4`: not clone work (SRE World, a data-engineering set, and take-home tasks).
  - `harbor-forge`: other people's work.
  - Local leftovers: a vendor-docs skill (`taiga-wiki`), debug logs (`_capture/`), and stashes for an unrelated project and a CI tweak.
- **`mockflow`**: a third-party repo (`benchflow-ai`).
