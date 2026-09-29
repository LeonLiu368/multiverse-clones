# Multiverse clones — collected

Everything I built for the Multiverse service-clone work at Abundant AI (June–July 2026),
gathered from the original repositories into one place with **full commit history**.

The original repos lived under `github.com/abundant-ai/` and are no longer reachable from my
account. This collection was assembled on 2026-09-29 from my local clones, which turned out to
be *more* complete than GitHub was: several branches had commits that were never pushed.

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

Every original commit is preserved **with its original hash**. Nothing was rewritten.

- `main` holds the root monorepo history plus each project, attached by a subtree merge.
- `archive/<repo>/<branch>` holds every original branch exactly as it was, at its original tip.
- `wip/abundant-slack-clone/slack-focused-implementation` is that branch plus a snapshot of
  uncommitted work found in the local checkout.

To see a project's pre-import history, read its archive branch. `git log -- spoink/` only shows
commits made after the import, because the original commits touched root-level paths.

```bash
git log --oneline archive/spoink/main
git log --oneline archive/abundant-slack-clone/slack-mcp-oss
```

| Original repo | Branch | Commits | Tip | Notes |
|---|---|---|---|---|
| multiverse-clones | `main` | 75 | `d5aec88d9` | root mainline |
| multiverse-clones | `leon/fleet-smoke` | 16 | `a66dbd130` | 1 commit never pushed |
| multiverse-clones | `leon/mv-image-naming` | 17 | `77d206c09` | merged into main |
| spoink | `main` | 59 | `6edc9837b` | |
| seed-dashboard | `main` | 33 | `a0f6caffa` | |
| abundant-identity | `main` | 1 | `0ccad93df` | never had a remote |
| abundant-slack-clone | `slack-mcp-oss` | 40 | `bae979766` | imported to `origins/`; 2 commits never pushed; contains `main` + `prebuilt-image-refactor` |
| abundant-slack-clone | `main` | 19 | `c680b1f31` | behind GitHub's main, which had merged `slack-mcp-oss` |
| abundant-slack-clone | `prebuilt-image-refactor` | 16 | `de98bb1ac` | never pushed |
| abundant-slack-clone | `mattermost-focused-implementation` | 11 | `62c2b0bcf` | prototype; 4 commits never pushed |
| abundant-slack-clone | `slack-focused-implementation` | 5 | `62a17e36e` | prototype; 1 commit never pushed |
| abundant-jira-clone | `main` | 8 | `17cf91d45` | 5 commits never pushed |
| abundant-jira-clone | `linear-graphql-surface` | 7 | `eabd19d81` | diverges from main |
| abundant-logfire-clone | `main` | 3 | `043b980f8` | |
| figma-clone | `main` | 6 | `3f54f708a` | |
| google-workspace-clone | `main` | 9 | `8b3d3427d` | 7 commits never pushed |

Uncommitted edits found in the multiverse-clones and figma-clone checkouts are the two
`Snapshot uncommitted local changes` commits on `main`.

## Not included

- **`gauge`, `ticketvector`, `gh-cli-clone`**: mostly or entirely other people's work (Owen and
  others). The monorepo already carries a snapshot of each in `clones/`.
- **Tasks from `abundant-ai/experiments`**: a shared repo holding everyone's work.
- **`mockflow`**: a third-party repo (`benchflow-ai`).
