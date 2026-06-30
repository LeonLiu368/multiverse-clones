# gh-cli-clone (`ghc`)

A **`gh`-compatible CLI and MCP server backed by a self-hosted [Forgejo](https://forgejo.org) forge.**
Runs fully offline. Built so an AI agent can do real repo / issue / PR work in a
sandboxed "world" — no `github.com`, no SaaS — using the same `gh` commands it
already knows.

This is the **gh-CLI clone** for the Multiverse/Worlds project: stand up a GitHub
stand-in, hydrate it from real repos (at a point in time), and let an agent operate
it. Validated end-to-end with a real model in Harbor (see [Agent validation](#agent-validation)).

```
agent ──calls──▶  gh  ─(shim)─▶  ghc CLI  ┐
                                          ├─▶  ForgejoClient  ──REST──▶  Forgejo (Docker, offline)
agent ──MCP───▶  ghc-mcp tools ───────────┘
harness ─────▶  ghc-hydrate  (operator only: build/seed the world)
```

One translation layer (`ghclone/forge/client.py`) maps gh-shaped operations onto
Forgejo's REST API. The CLI, the MCP server, and the hydration tools are thin
layers over it — so parity is structural, not duplicated.

---

## Why Forgejo
GitHub-shaped forge primitives (repos, issues, PRs, reviews, labels, Actions,
auth) with **no SaaS dependency**. The one real mismatch is **no GraphQL** — `ghc`
re-expresses gh's GraphQL operations as REST. See [Gaps](#known-gaps).

## Quickstart (offline, uv)

```bash
# 0. bring up the whole stack: forge + token + act_runner (so Actions execute)
bash scripts/up.sh
export GHC_HOST=http://localhost:3300 GHC_TOKEN=$(cat ghc-token.txt)

# 1. install (uv-managed)
uv sync --extra dev                       # or: uv pip install -e .

# 2. use it like gh
uv run ghc auth status
uv run ghc repo create demo -d "hello"
uv run ghc issue create -R ghc-admin/demo -t "first issue" -b "body"
uv run ghc pr create  -R ghc-admin/demo -t "fix" -H feature -B main
uv run ghc pr review 1 -R ghc-admin/demo --approve
uv run ghc pr merge  1 -R ghc-admin/demo --method squash
```

## Install as `gh` (drop-in replacement)

It installs as **`ghc`** by default so it never shadows a real `gh` during dev.
To make the `gh` command itself resolve to this clone — so an agent or script
that calls `gh …` transparently hits the offline forge — pick one:

```bash
# point it at the forge (real-gh env var names; GHC_HOST/GHC_TOKEN also work)
export GH_HOST=http://localhost:3300 GH_TOKEN=$(cat ghc-token.txt)
```

**Option A — PATH shim (no install; best for a sandbox/CI).**
`scripts/gh` forwards `gh …` → `ghc`. Put it first on `PATH`:
```bash
export PATH="$PWD/scripts:$PATH"
gh auth status          # now runs the clone
```

**Option B — shell alias (quick, interactive use).**
```bash
uv sync --extra dev
alias gh='ghc'          # ghc is on PATH after install
```

**Option C — standalone `gh` binary (PyInstaller; no Python on the target).**
This is what the sandboxed tasks ship — a single compiled `gh` with no source to
read:
```bash
printf 'from ghclone.cli.main import _main\nif __name__=="__main__": _main()\n' > ghentry.py
uv run pyinstaller --onefile -n gh --collect-submodules ghclone ghentry.py
sudo cp dist/gh /usr/local/bin/gh        # `gh` is now the clone, system-wide
```

All three present the exact `gh` surface (help, errors, `--json`, success
messages — see [output emulation](#output-emulation--indistinguishable-from-real-gh)).
The token can also be delivered as a file at `/run/secrets/token` or `~/.config/gh/hosts.json`.

## Container image (public registry)

The gateway is the canon **image trio** (Clone Standard R2). **Published publicly
to GHCR under `abundant-ai`, multi-arch (`linux/amd64,linux/arm64`):**

| Image (tag) | What it is | Data delivery |
|---|---|---|
| [`ghcr.io/abundant-ai/ghc-service`](https://github.com/orgs/abundant-ai/packages/container/package/ghc-service) (`:latest`) | base — Forgejo + gh CLI/MCP + Actions runner, **no data** | — |
| `ghc-service:empty` | the base; boots an empty forge | per-task fixture **mounted** at `/fixture` |
| `ghc-service:prod-v1` | the **corpus DB baked into the image** | none — boots mount-free and serves the corpus as-is |

Switching a task between an empty workspace and the shared corpus is the **image
tag alone** (`:empty` + a `/fixture` mount ↔ `:prod-v1`). The image trio is built
from `selfcontained/gateway/` (`Dockerfile`, `Dockerfile.prod-v1`,
`gateway-entrypoint.sh`, `corpus-seed.sh`).

```bash
docker pull ghcr.io/abundant-ai/ghc-service:prod-v1   # corpus baked in
# or build the whole trio locally (no pull needed):
scripts/images.sh build        # ghc-service:{latest,empty,prod-v1}
```

Republish with `scripts/images.sh` (registry-parameterized; defaults to GHCR
under the `abundant-ai` org) — or just merge to `main` (the
[`Publish Service Image`](.github/workflows/publish-images.yml) workflow rebuilds
and pushes it):

```bash
# 1. authenticate to the registry (GHCR needs a token with write:packages)
scripts/images.sh login          # prints the exact gh-refresh + docker-login steps

# 2. build + push the trio (override REGISTRY as needed)
REGISTRY=ghcr.io/abundant-ai scripts/images.sh build   # builds {latest,empty,prod-v1}
scripts/images.sh push                                 # or: scripts/images.sh all
scripts/images.sh buildx-multiarch                     # multi-arch build+push (amd64,arm64)
```

Tasks should use `ghc-service` as a sidecar and copy `/usr/local/bin/gh` (or
`ghc`) from it into the thin agent `main` image, exactly like the
Slack/Linear incident tasks copy `slack`, `linear`, and `jira` from their service
images. See [Task integration](docs/task-integration.md).

### Sharing without a registry

No registry (or no permission to create org packages)? The gateway carries both
`build:` and `image:` in every task compose (R1.5): `docker compose build` tags
the pullable `ghcr.io/abundant-ai/...` name **locally**, so `up` uses the local
build and never pulls — no GHCR auth needed. To build the trio from source:

```bash
git clone https://github.com/abundant-ai/gh-cli-clone && cd gh-cli-clone
scripts/images.sh build          # builds ghc-service:{latest,empty,prod-v1}, no pull needed
```

## As an MCP server
```bash
uv run ghc-mcp        # stdio transport; point your agent/client at it
```
Exposes the agent surface (repo / issue / pr / label / milestone / workflow / run /
api) as MCP tools — the **same** `ForgejoClient` as the CLI. Hydration is **not**
exposed to the agent (see [Agent boundary](#agent-boundary)).

---

## Command parity

### P0 — repos, issues, PRs (the daily drivers) ✅
| Group | Commands |
|---|---|
| `auth` | `login`, `status`, `logout`, `token` |
| `repo` | `list`, `view`, `create`, `delete`, `clone`, `fork`, `rename`, `edit` (+topics) |
| `issue` | `list` (+`--label/--milestone/--search/--state`), `view` (+comments), `create`, `comment`, `close`, `reopen`, `edit`, `react` |
| `pr` | `list`, `view`, `create`, `diff`, `checkout`, `merge`, `close`, `reopen`, `review` (approve·request-changes·comment) |
| `api` | REST pass-through (`-X`, `-f`, `--paginate`) + GraphQL guard |

### P1 — Actions, code review, comments, metadata ✅ (3 gaps)
| Group | Commands |
|---|---|
| `label` | `list`, `create`, `delete` |
| `milestone` | `list`, `create` |
| `workflow` | `list` (repo files), `run` (dispatch) |
| `run` | `list` (Actions tasks) |
| reactions / review | `issue react`, `pr review` |

Full feature list, command list & gh parity: **[docs/PARITY.md](docs/PARITY.md)**.
Per-command Forgejo endpoint mapping: [docs/COMMANDS.md](docs/COMMANDS.md).

---

## Output emulation — indistinguishable from real `gh`

Parity isn't enough: an agent that knows GitHub CLI can tell a wrapper apart by
*output format*. Every agent-visible surface is matched to **gh 2.89** — verified
against the installed binary (help/errors) and the [`cli/cli`](https://github.com/cli/cli)
source (success strings):

- **Help** renders in gh's cobra layout (`USAGE / CORE COMMANDS / FLAGS / LEARN
  MORE`), not Click/Typer's. **Errors** are cobra-phrased (`unknown command "x"
  for "gh"`, `unknown flag: --x`, `accepts 1 arg(s)…`). `gh --version` matches.
- **No rich tells**: list output is borderless (gh columns / TSV when piped), not
  box-drawing tables; no `╭─ Error ─╮` panels; no Typer completion flags.
- **Success messages verbatim from gh source** — `create` prints the URL to
  stdout; `✓ Closed issue OWNER/REPO#N (Title)`, `✓ Squashed and merged pull
  request OWNER/REPO#N (Title)`, `auth status`'s multi-line block — right text,
  icon, color, and stream.
- Commands gh lacks (`milestone`, `issue react`, `run artifacts`) are hidden from
  `--help` (still callable).

A 52-path audit harness confirms zero framework artifacts. Full per-command
fidelity table + coverage matrix: **[docs/GH-EMULATION-AUDIT.md](docs/GH-EMULATION-AUDIT.md)**.

---

## Hydration — turn a real GitHub repo into an offline world
Operator tooling (`ghc-hydrate`), two engines:

- **Engine A — native migrate** (one call): `ghc-hydrate migrate <github-url>` pulls
  git + issues + PRs + comments + labels + milestones + releases via Forgejo's
  GitHub downloader. Preserves issue/PR numbers.
- **Engine B — snapshot + replay** (offline, reproducible):
  `ghc-hydrate snapshot OWNER/REPO --out DIR` freezes GitHub to a committable
  artifact, then `ghc-hydrate apply DIR --into o/r` replays it into Forgejo with
  no GitHub access — author remap (Sudo / ghost provenance), gap placeholders, PR
  fallback.

**Point-in-time** (`--as-of <commit-sha|ISO-timestamp>`): hydrate the repo **and its
issue tracker** as they were at a moment — git cut to the commit, issues/PRs
filtered and state-reconstructed from the timeline (open-at-T, labels-at-T,
title-at-T), comments truncated. Built for "drop the agent in *before* the fix."
See [docs/HYDRATION.md](docs/HYDRATION.md).

---

## Agent boundary
World-building must not be reachable by the agent under test. So:
- **Agent surface** (`ghc` CLI, the `gh` shim, `ghc-mcp`): gh parity only.
- **Operator surface** (`ghc-hydrate`, separate entrypoint): migrate / snapshot /
  apply / verify.

`ghc hydrate …` does not exist; the agent MCP exposes no hydration tools; the
baked task image (`scripts/build-agent-image.sh`) inherits this — even with a
token, the agent can't hydrate. Enforced by tests.

### Container isolation (the agent can't see — or *name* — the implementation)
A single-container task leaks: the agent can `cat /var/lib/forgejo/conf/app.ini`,
read the `gh` wrapper source, and hit the forge directly — so it *knows* it's
Forgejo. The **isolated** layout (`examples/oddish-tasks/incident-isolated`,
harbor compose mode) fixes that:

- **The git host runs in a separate sidecar** — a different container with its
  own filesystem. The agent's `main` container can't read `app.ini`, the server
  binary, the data dir, or the token-gen.
- **The sidecar has no telltale name or port.** It's reachable **only by static
  IP on port 80** (`http://10.88.0.2`) on the compose *default* network, so every
  URL the agent sees — clone remotes, PR links, `git push` hints, errors — is a
  bare IP with no port, never a `forge`/`github` hostname and no `:3000`
  (Gitea-default) tell. Reverse-DNS (`getent hosts`) gives only a generic `api`
  service on a stock `default` network.
- **`gh --help` and every message are scrubbed.** Help text, the graphql guard,
  auth hints, and the workflow-list hint use GitHub-neutral wording — no
  `Forgejo`/`forge`/`ghc`/`.forgejo`. The PR URL is normalized `/pulls/` → `/pull/`
  (GitHub's singular shape).
- **`gh` is a compiled binary** (PyInstaller) in `main` — no Python source to read.
  `forgejo`/`gitea`/`ForgejoClient` are **zero** in its strings; the only residual
  is the frozen module path `ghclone.forge`, reachable solely by `grep -a`-ing the
  executable (there's no `strings`/`file` in the container).
- **No token in any output.** `gh` configures a git credential helper (exactly
  like real `gh`), so `git remote -v` shows a clean URL and the token never lands
  in a remote. Env surface uses real-`gh` names (`GH_HOST`/`GH_TOKEN`).
- **Errors are wrapped.** API failures print `error: HTTP 422: <message>` — never
  the backend's `/api/v1/...` URL or any "forge" wording.
- Neutral identifiers throughout: repo owner `acme`, host an IP, no `ghc-*` tells.

Verified from the agent's `main` view: `gh auth status` → "http://10.88.0.2 as
acme", `git remote -v` → `http://10.88.0.2/acme/webapp.git` (no token), PR →
`http://10.88.0.2/acme/webapp/pull/2`, `cat app.ini` → *No such file*, no server
binary. Passes on oddish ([experiment 90910e4b](https://www.oddish.app/share/im55qyNINv4f8xwFfr5rCi7mOl1-bGRoGczRRyTNXcM)),
oracle **and gemini** (real agent) both 1.0. Decisive: the final gemini
trajectory shows **zero** `forge`/`forgejo`/`gitea`/`:3000`/`/pulls/` in the
terminal *and* **zero backend guesses anywhere in its private reasoning** — it
treats the host as a plain remote at an IP, indistinguishable from a private
GitHub Enterprise endpoint.

> The design hardened across three iterations on this experiment: the first
> isolated run ([6e70115e](https://www.oddish.app/share/cvAlawa8O6ybiczAFGlI1sIBLx8aMsxFsatqEOvggQQ)) proved the
> filesystem sandbox but leaked `forge:3000` in URLs and a `forge error:` prefix;
> the trajectory then caught the agent *inferring* "Gitea/Forgejo" from the `:3000`
> port and `/pulls/` path, and `gh --help` text naming Forgejo. Static-IP+port-80,
> URL normalization, and the help/message scrub closed each in turn — ending at a
> trajectory with no leak and no inference.

**The entire `examples/oddish-tasks/` suite uses this layout** (run
`scripts/migrate-isolated.sh` to (re)generate it). All 12 tasks + their Actions
variants pass on oddish under one experiment
([a93c3e97](https://www.oddish.app/share/GWMGqWjBqhtBYJ6cHtrditXMm4nmnP573-JWMFlfoNg)): **17/17 trials green**
(oracle on all 12, gemini on 5), including `ci-artifact` running a real workflow
on a runner *inside the sidecar* (dispatch → execute → `gh run download`). Across
all 5 gemini trajectories the agent-visible terminal shows **zero**
`forge`/`forgejo`/`gitea`/`:3000`/`.forgejo`/`runs-on: host` — the only backend
words appear when the agent *brainstorms candidates* for the IP host and lists
"Gitea **or GitHub Enterprise**", unable to tell which. That's the irreducible
floor: a private host speaking GitHub's API is indistinguishable from GHE, which
is exactly the goal.

Actions tasks get a runner *in the sidecar* (`Dockerfile.forge-actions` +
`forge-entrypoint-actions.sh`): a host-mode `forgejo-runner` registered as
`ubuntu-latest:host`, so seeded workflows use GitHub's canonical
`runs-on: ubuntu-latest` under `.github/workflows` — no execution detail reaches
the agent.

---

## Agent validation
Proven that a **real model can use `ghc` for what it needs**, end-to-end in Harbor
against the offline forge. The `gh` in the task image is our clone; the verifier
recomputes truth from the forge.

Sample tasks (`examples/tasks/`, model = `gemini/gemini-3.5-flash`, agent `terminus-2`):

| Task | Exercises | oracle | nop | gemini pass@3 |
|---|---|:--:|:--:|:--:|
| `p0-open-issue` | `gh issue create` | 1 | 0 | **3/3** |
| `p1-triage` | `gh label create` + `issue comment` + `issue close` | 1 | 0 | **3/3** |
| `p0-fix-pr` | `gh repo clone` + git + `gh pr create` | 1 | 0 | **3/3** |

`nop=0 / oracle=1` holds for every task, so each measures the real capability.
gemini-3.5-flash drives the full P0+P1 surface — including the multi-step
clone→branch→edit→push→PR loop — through our `ghc`. Trajectories show genuine tool
use, e.g. *"use `gh auth status` to confirm … then `gh issue create`."*

> **Failure-analysis note (kept on purpose).** `p0-fix-pr` first scored 0/3. The
> trajectory showed gemini producing a *correct* fix and PR — so the fault was the
> task, not the model: the verifier string-matched and forbade any `return a / b`
> line, which a correct multi-line fix still has for the non-zero branch (the
> oracle's one-liner slipped past, masking it). Rewritten to test *behavior*
> (`div(1,0)==0`, `div(6,2)==3`) → 3/3. This is the over-strict-verifier failure
> mode the eval brief warns about, caught and fixed.

Reproduce:
```bash
scripts/build-agent-image.sh                       # base image (gh = ghc, agent surface)
uv run python scripts/seed_tasks.py                # seed the forge repos
harbor run -p examples/tasks/p0-fix-pr -a oracle   # then -a nop, then -a terminus-2 -m gemini/gemini-3.5-flash
```
More detail + trajectory excerpts: [docs/HARBOR.md](docs/HARBOR.md).

### Self-contained "world" tasks (forge bundled — oddish/cloud-ready)
The tasks above point at a host forge. For cloud sandboxes (oddish/Daytona) that
can't reach a local forge, `examples/oddish-tasks/` bundles **Forgejo inside each
task container** — booted + seeded by the task's healthcheck, with `gh` wired to
it. No compose, no external network; uploads to oddish as-is.

Validated in harbor (local) **and on oddish** (cloud, Daytona) with `terminus-2` +
`gemini-3.5-flash` — oddish experiment **[dca8467c](https://www.oddish.app/share/KRJ5OfOabLbBMjl9cCASs-GkRt48PegkD4F6qg45OTg)**,
all three **passed (reward 1.0)**:

| Task | Exercises | oracle | nop | gemini local | gemini **on oddish** |
|---|---|:--:|:--:|:--:|:--:|
| `p0-issue` | `gh issue create/comment/close` | 1 | 0 | 2/2 | **✅ 1.0** |
| `p1-triage` | `gh label create` + `issue comment/close` | 1 | 0 | 2/2 | **✅ 1.0** |
| `p0-fix-pr` | `gh repo clone` + git + `gh pr create` | 1 | 0 | 2/2 | **✅ 1.0** |

The cloud trajectory matches local: the agent ran `gh repo clone` → `git checkout
-b` → edit → `git push` → `gh pr create` in the Daytona sandbox against the
in-container forge, and passed — so `ghc` works as a `gh` drop-in in the same cloud
harness real tasks use.

### Comprehensive command coverage — agents use *every* command
**`cmd-coverage`** drives the entire command surface in one task — auth/api, repo
(view/list/edit/clone/fork/rename), issue (create/view/list/comment/edit/close/
reopen), label (create/list/delete), pr (create/view/list/diff/review/merge),
release (create/list), and the full Actions flow (`workflow run` → `run list/view`
→ `run download` artifact). Its verifier checks 7 independent end-state markers
spanning all groups. Focused `cmd-*` tasks cover overlapping subsets:

| Task | Commands the agent is required to use |
|---|---|
| `cmd-coverage` | **every** command (auth·api·repo·issue·label·pr·release·workflow·run) |
| `cmd-issues` | `repo create/view/delete/rename` · `label list/create/delete` · `issue create/comment/edit/react/close/reopen` |
| `cmd-pr` | `repo fork/clone` · `pr create/review/merge` · `issue close` · git |
| `cmd-actions` | `workflow list/run` · `run list` |

Coverage matrix (command → task): **[docs/GH-EMULATION-AUDIT.md](docs/GH-EMULATION-AUDIT.md)**.
Trajectory grep confirms the agent actually runs them — no skepticism that breaks
the task; it just uses `gh`.

**Full per-command map** (✅ verifier-required · 🔍 trajectory-confirmed · 🧪 harness):
[docs/COMMAND-COVERAGE.md](docs/COMMAND-COVERAGE.md).

**CI-diagnosis without a live runner.** `gh run view --log-failed`, `gh pr checks`,
and `gh workflow view` render GitHub-shaped runs/jobs/steps/logs from a per-world
seed, deterministically — see **[docs/ACTIONS-OVERLAY.md](docs/ACTIONS-OVERLAY.md)**.

> The `cmd-*` tasks above are deliberately a **command smoke test** — the
> instruction *lists* the operations. They prove every command works for an agent,
> but they're **not realistic**. The task below is the realistic counterpart.

### Realistic scenario suite — `gh` emerges from the work
Goal-framed tasks with **no command list**; verifiers check the **outcome**, not
the commands. **All 6 pass on oddish** ([experiment 398031e0](https://www.oddish.app/share/WL1-IuDFLEt-_DDU2ud2UQ_znp33iVfr8z5mG7CvBqw),
reward 1.0) — oracle=1, nop=0, gemini local too:

| Task | Scenario (no commands named) | Commands the agent *chose* |
|---|---|---|
| `incident-fix` | on-call: fix a prod incident, ship via a reviewed PR, resolve it | issue list/view → repo clone+git → pr create → **pr review** → pr merge → issue close |
| `triage-sweep` | triage an untriaged backlog: label real bugs, milestone them, close dupes | issue list/**view** → issue **edit** (label+milestone) → issue comment → issue close |
| `release-prep` | cut the v1.0 release: resolve blocker, close milestone, publish | issue list → issue close → **milestone close** → **release create** |
| `dep-bump` | security advisory: bump a vulnerable dep via PR + tracking issue | repo clone+git → pr create → issue create |
| `pr-review` | review an open PR, send it back, then reopen for another look | pr list → **pr checkout** → **pr diff** → **pr close** → **pr reopen** |
| `ci-artifact` | trigger the CI build, wait, download the build artifact, file the code | **workflow run** → **run watch/list** → **run download/artifacts** → issue create |

`ci-artifact` runs an **in-container host-mode `act_runner`** (no docker-in-docker),
so the workflow **actually executes** and the agent `gh run download`s the artifact
it produced — the full Actions + artifact path, end-to-end in one container.

The agent **discovered** each workflow from intent — e.g. `incident-fix` it *inferred*
`gh pr review --approve` from "reviewed PR"; `triage-sweep` it read each issue with
`gh issue view` and *decided* which were bugs vs duplicates before acting. No
task-breaking skepticism — it reaches for `gh` to **do the work**, not because told.

**Trajectory analysis** (what the agent actually did): it uses `gh` *as if it were
the real GitHub CLI* — `gh auth status` to confirm, explores `gh label/issue
--help` for syntax, then `gh label create -R … -n wontfix`, `gh issue create -R -t
-b`, `gh repo clone`, `git checkout -b` → edit → `git push` → `gh pr create -H -B`.
Standard gh muscle memory, and every task completes.

> **Honest caveat:** in **1 of 6** trajectories the agent noticed `gh` is *"a
> mock/wrapper CLI"* (from the typer-style `--help` output) — and **still completed
> the task**. So it's a functional drop-in (the agent always succeeds), but the help
> text can reveal the implementation. We set the program name to `gh` to cut the
> obvious tell; fully gh-identical help formatting is a follow-up.

---

## Testing
```bash
uv run pytest -q          # 55 tests: offline + live integration + exhaustive coverage
                          # (live ones auto-skip without GHC_HOST/GHC_TOKEN)
```
- `test_client.py` — `ForgejoClient` over a mocked httpx transport (request shaping, pagination, errors, Sudo).
- `test_cli_unit.py` — agent CLI with a mocked client (args, output, exit codes).
- `test_hydrate_unit.py` — temporal reconstruction edge cases, apply plan, verify drops.
- `test_smoke.py` — config, CLI/MCP surface, **agent-boundary** assertions.
- `test_integration.py` — live issue + PR + P1 lifecycles against a running Forgejo.
- `test_coverage_live.py` — **exhaustive**: every agent command via the `gh` shim (`scripts/agent-coverage.sh`), 41/41 (the harness parses the resource URL `ghc … create` prints, e.g. `…/issues/3`).
- `test_parity.py` — **CLI↔MCP parity** (R6.2): per group, `ghc … --json` and the matching `ghc-mcp` tool return the same records (live).
- `test_isolation.py` — **agent isolation** (R6.3): no forge state on disk, `import ghclone` raises, no api/seed source on the agent.

## Known gaps
- **GraphQL** — none on Forgejo; `gh api graphql` errors by design.
- **Artifacts** — `gh run download` **is implemented** over Forgejo's web artifact
  route (verified round-trip). Caveat: use `upload/download-artifact@v3` — the v4
  actions refuse non-github.com hosts.
- **Actions execution** — supported: `scripts/start-runner.sh` registers an
  `act_runner` and pushed workflows execute (verified push → `success`). A GitHub
  Actions *subset* (no Marketplace; actions by full URL). Without a runner, jobs queue.
- **`gh api --jq`** — not implemented (pipe to `jq`).

## Layout
```
ghclone/forge/client.py   # the gh→Forgejo REST translation layer (all logic)
ghclone/cli/main.py       # ghc — agent CLI (gh parity)
ghclone/cli/admin.py      # ghc-hydrate — operator CLI (world-building)
ghclone/mcp/server.py     # ghc-mcp — agent MCP (no hydration)
ghclone/hydrate/          # snapshot / apply / temporal / verify
docker/docker-compose.yml # Forgejo (+ act_runner for P1)
examples/tasks/           # P0/P1 Harbor sample tasks
scripts/                  # bootstrap, gh shim, acceptance, build-agent-image, seed
docs/                     # COMMANDS, HYDRATION, ACCEPTANCE, HARBOR
```
