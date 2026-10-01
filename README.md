# Multiverse clones

Working copies of the software tools engineers use every day (Slack, Jira, Figma, Grafana,
GitHub and more), rebuilt so an AI agent can be tested against them. Alongside the clones are
the tools for filling them with realistic data and for checking that they behave like the real
thing.

I built this at Abundant AI in June and July 2026 as part of the Multiverse project. This
repository collects that work in one place, with its full commit history.

## The idea

Most coding benchmarks hand an agent a repository and a failing test. Real engineering work
rarely looks like that. The bug report is in Jira, the discussion about the fix is buried in a
Slack thread, the design spec is in Figma, and the error that proves it is in Grafana. A good
engineer's skill is going and finding those facts and checking them. Writing the code is the
easy part.

To test that skill you need an environment where the facts actually live inside those tools,
and the agent has to use the tools to get them. Each clone here is a stand-in for a real
service: it speaks the same API, holds seeded data, and gives the agent the same command-line
tool and MCP server it would use on the real product.

## How a clone works

Every clone runs as two containers:

```
┌──────────────────────┐      HTTP      ┌─────────────────────────┐
│  agent container     │ ─────────────▶ │  gateway container      │
│                      │                │                         │
│  the CLI and MCP     │ ◀───────────── │  the clone's API        │
│  tools, the codebase │                │  and all of its data    │
│  NO data             │                │  NOT visible to agent   │
└──────────────────────┘                └─────────────────────────┘
```

The **gateway** holds the data and serves the API. The **agent** container holds only the
tools. The agent never sees the data files on disk, so the only way to learn what's in Slack is
to actually query Slack. This split is what keeps tasks honest; every shortcut I found an agent
taking traced back to data it could reach without calling a tool.

A few rules follow from that, and every clone keeps them:

- The CLI and the MCP server are both thin wrappers around the same API, so they can't drift apart.
- The API matches the real product's API as closely as possible, including default filters and
  flag names, so an agent's real-world habits carry over.
- Where a clone doesn't cover part of the real service, its README says so.

The full contract is **Clone Standard v1**, in [`skills/_shared/clone-standard.md`](skills/_shared/clone-standard.md).

## The clones

All 11 live in [`clones/`](clones/). Each folder is the complete source for that clone: the API
server, the CLI, the MCP server and its Dockerfiles. Every clone has at least one example task,
either in its own folder or in [`experiments/fleet-smoke/`](experiments/fleet-smoke/).

| Clone | Stands in for | What it covers |
|---|---|---|
| [`abundant-slack-clone`](clones/abundant-slack-clone) | Slack | Web API channels, history, threads, search and posting; the open-source `slack-mcp` server |
| [`abundant-jira-clone`](clones/abundant-jira-clone) | Jira and Linear | Issues, comments and states, with a Linear-style GraphQL API |
| [`figma-clone`](clones/figma-clone) | Figma | Design files as node trees, components, styles, versions and comments |
| [`grafana-clone`](clones/grafana-clone) | Grafana | The HTTP API plus Loki log and Prometheus metric queries |
| [`gh-cli-clone`](clones/gh-cli-clone) | GitHub | A `gh`-compatible CLI and MCP, backed by a self-hosted Forgejo server |
| [`sentry-clone`](clones/sentry-clone) | Sentry | Issues and events, with real search filters and sort order |
| [`abundant-logfire-clone`](clones/abundant-logfire-clone) | Pydantic Logfire | Traces and spans; accepts live OpenTelemetry data |
| [`aws-clone`](clones/aws-clone) | AWS | S3, Kinesis, and IAM policy simulation |
| [`notion-clone`](clones/notion-clone) | Notion | Pages, blocks, databases with filter and sort queries, search, comments |
| [`google-workspace-clone`](clones/google-workspace-clone) | Gmail, Calendar, Drive | Loads real Google Takeout exports |
| [`discord-clone`](clones/discord-clone) | Discord | REST API v10, message search, paginated history |

[`clones/MANIFEST.json`](clones/MANIFEST.json) records which upstream commit each folder was copied from.

## What else is here

| Folder | What it is |
|---|---|
| [`skills/`](skills/) | Two Claude skills that build and check clones. `clone-creation` builds a new clone to the standard; `clone-audit` tests one and writes a pass/fail report with fixes. Running the two in a loop is how all the clones were brought up to the same bar. |
| [`experiments/fleet-smoke/`](experiments/fleet-smoke/) | One small task per clone, nine in total. Each is run three ways: an agent that does nothing (must score 0), the reference solution (must score 1), and one real model. It's a cheap check that the whole fleet still works end to end. |
| [`experiments/pull-smoke/`](experiments/pull-smoke/) | A Notion task whose environment contains no clone source at all, just two files that pull published images. Proof that tasks can stay small. |
| [`live/`](live/) | Early work on live-deployment tasks: a real open-source app running on Kubernetes, sending telemetry to the Logfire clone, graded by how the app behaves under load after the agent's fix. |
| [`viz/`](viz/) | The parity dashboard. For each clone it shows the seeded data rendered like the real product, the command an agent would run, the real API it corresponds to, and a score for how closely the clone's response matches the real one. |
| [`spoink/`](spoink/) | The snapshot engine. It captures data from real Slack, Linear, GitHub and Logfire accounts, rewinds it to the moment an incident happened, and packages it into a clone's gateway so a task can start from that exact point in time. |
| [`seed-dashboard/`](seed-dashboard/) | A viewer for the data seeded into a clone, drawn to look like the real product. You can also edit that data and download the changes, so a task is built from exactly what you looked at. |
| [`abundant-identity/`](abundant-identity/) | Maps the same anonymized person across the Slack and Jira exports, so one person has one name in every clone. |
| [`origins/`](origins/) | The standalone repositories five of the clones started in, with their early development history and some files that never made it into `clones/`. |
| [`docs/`](docs/) | [`COLLECTION.md`](docs/COLLECTION.md) explains where everything came from and how the commit history is organized. [`ci-reference/`](docs/ci-reference/) keeps the old image-publishing workflows for reference. |

## Example tasks

Two tasks show the shape well.

**`slack-incident-fix-report`** ([fleet-smoke](experiments/fleet-smoke/tasks/slack-incident-fix-report))
An error-budget monitor has the wrong alert thresholds, and its tests fail. The correct values
were agreed in an SLO review that only ever happened in Slack. The agent has to find the final
agreed thresholds, fix the code, and post a notification to `#error-budget-reports` saying which
thresholds it applied.

**`figma-spec-recovery`** ([fleet-smoke](experiments/fleet-smoke/tasks/figma-spec-recovery))
A pricing card component ships placeholder values. The visible tests only check the *shape* of
the spec. The real values live in a Figma file and a comment thread on it, and the agent has to
use the Figma tools to get them.

What makes tasks like these hard isn't the code. It's the earlier proposals that were later
revised, the similar-looking channels that have nothing to do with the problem, and search
results that are noisy on purpose. An agent that trusts the first thing it finds gets it wrong.

## Running things

These instructions assume you're at the root of this repository.

**The parity dashboard** needs nothing but Python:

```bash
cd viz && python3 -m http.server 8770
# open http://localhost:8770
```

**The seed dashboard** needs Python 3 and Node. It reads the clones in this repo by default:

```bash
./seed-dashboard/run.sh
# open http://localhost:5273
```

The Jira viewer also needs the `ticketvector` repository, which isn't in this collection. It
looks for a checkout next to this repo; set `TICKETVECTOR_BASE` to use one somewhere else.

**Spoink** installs as a Python package:

```bash
cd spoink && pip install -e ".[dashboard]" && python -m spoink.dashboard
# open http://localhost:8787
```

Capturing real data needs API tokens for the source accounts in a `.env` file. The Abundant
accounts it was built against are no longer available to me, so a capture needs your own.

**The tasks** are written for [Harbor](https://github.com/harbor-framework) and Oddish, and
each one pulls its gateway and agent images from `ghcr.io/abundant-ai/`. Most of those images
are no longer publicly pullable; when I checked on 2026-09-30, only `logfire-service` and
`gworkspace-service` were. To run a task now, build the images from that clone's folder in
`clones/` and point the task's `docker-compose.yaml` and `Dockerfile` at your local tags.

## A note on data

Some tasks here include **real data**:

- A company's Jira export: 8,040 issues and about 270 personal email addresses
  (`clones/abundant-jira-clone/selfcontained/base/data/eng-prod-state.json`, also under `origins/`).
- A Slack export with real names (`…/rw-large-slack-read/environment/data/slack-export/`).
- My own Gmail, Calendar and Drive data from Google Takeout (the `gws-event-room` and
  `gws-real-projects` tasks).

This repository should stay private. The data is also in the commit history, so deleting the
files wouldn't remove it.

## What was left unfinished

- **Live environments.** Spoink produces snapshots of a moment in time. The next step was to have
  agents act against a running system instead, and `live/` is only the first spike toward that.
- **Data that changes during a task.** New messages arriving while the agent works, so it has to
  keep checking. Designed, never built.
- **An automated task pipeline.** Spoink's task creator can find incidents and turn them into
  candidate tasks, but the full find, classify, generate, validate, publish loop was never
  finished.

## History

Every original commit is preserved with its original hash, and each original repository's
branches are kept under `archive/`. See [`docs/COLLECTION.md`](docs/COLLECTION.md) for how the
history is organized and a table of every original branch.
