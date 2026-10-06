# apex-swe-clones

APEX-SWE **Observability** tasks ([mercor/APEX-SWE](https://huggingface.co/datasets/mercor/APEX-SWE),
CC-BY-4.0) re-platformed onto abundant-ai's service clones.

## Why

APEX's Observability tasks recreate a production incident with a six-container stack —
lightweight Plane (Django + Postgres + Redis), lightweight Mattermost, real Loki +
Grafana — at ~8 GB RAM / 40 GB disk and 180–240s startups per task. We keep the task
*content* and swap the *substrate* for three published, deterministic clone images:

| APEX service | Clone | Image |
|---|---|---|
| Plane (issues) | ticketvector | `ghcr.io/abundant-ai/ticketvector-service:main` |
| Mattermost (chat) | slack-service | `ghcr.io/abundant-ai/slack-service:latest` |
| Loki + Grafana + Prometheus | gauge | `ghcr.io/abundant-ai/gauge-service:main` |

**Preserved verbatim:** the upstream repo @ `base_commit` (cloned at build), the planted
bug, `solution/golden.patch`, `tests/test.patch`, `tests/test_metadata.json` (F2P/P2P),
and the incident *content* (issue text, chat thread, log lines). Grading runs the repo's
own test suite on `/app/repo` after applying `test.patch` — fully independent of the clones,
which are only the diagnostic surface.

## Layout

```
apex-swe-clones/
├── apex-swe-clones-manifest.yaml   # Oddish experiment manifest
├── tools/
│   ├── apex_to_clones.py           # converter: APEX fixtures -> clone seeds
│   └── SCHEMAS.md                  # the three clone seed schemas (authoritative)
└── tasks/<task>/
    ├── task.toml                   # mcp_servers: slack (slack-mcp), grafana (mcp-grafana)
    ├── instruction.md
    ├── environment/
    │   ├── Dockerfile              # repo base image + multi-stage COPY of clone CLIs/MCP
    │   ├── docker-compose.yaml     # main + ticketvector/slack/gauge sidecars
    │   └── data/{ticketvector,slack,gauge}/...   # converter output
    ├── solution/{golden.patch,solve.sh}
    └── tests/{test.sh,stage_data.sh,run_verifier.sh,test.patch,test_metadata.json}
```

## Recipe (convert one Observability task)

Source = an `apex-swe-variants` task (repo+patches already extracted) or the raw APEX task.

1. **Stage** the source fixtures: `data/plane/issues.json`, `data/mattermost/scraped.json`,
   `data/loki/logs.json`, plus `golden.patch`, `test.patch`, `test_metadata.json`.
2. **Convert** the diagnostic surface:
   ```
   python tools/apex_to_clones.py --from-variant <src> \
     --out tasks/<task>/environment/data \
     --workspace meridian --project-key <KEY> --service <service-name>
   ```
   Mappers: Plane issues → ticketvector `state.json` (issue assigned to `agent`);
   Mattermost → slack `scraped.json` (author flattened to a username string);
   Loki streams + Grafana → gauge `state.json` (logs become `entries[]`; gauge's
   label+`|=` filter engine serves any plausible LogQL query; `meta.now` is anchored
   just after the last log so default time windows include it).
3. **Copy** the pass-through artifacts into `solution/` and `tests/`.
4. **Author** `Dockerfile` (repo's language base image; clone `git clone` @ base_commit;
   multi-stage `COPY --from` the clone CLIs + MCP + `/opt` packages), `docker-compose.yaml`
   (copy from an existing task — the clone sidecars never change), `task.toml`,
   `instruction.md`, `solution/solve.sh` (`git apply golden.patch`), and the verifier
   scripts (`run_verifier.sh` runs the repo's own test command from `test_metadata.json`).

## Brittle hidden tests → discoverable spec (`--spec`)

Many APEX F2P tests pin an **exact implementation interface** the agent can't infer, so a
semantically-correct fix is graded 0 (only the oracle passes). Two flavours seen in the pilot:

- **Private-symbol imports** — paperless's `test_lock_backoff.py` does
  `from documents.search._backend import _LOCK_BACKOFF_CAP, ...`. A fix with different names
  fails at import ("BAD_FAILURE – Underspecified Instruction").
- **Rigid call signatures** — bor's `eth/peer_test.go` calls `doWitnessRequest(..., cancel)` /
  `buildWitnessRequests(..., cancel)` with a new final `cancel <-chan struct{}` param. A fix
  that solves the same leak a different valid way (e.g. exposing `Request.Done()`) fails to
  **compile** ("BAD_FAILURE – Rigid/Brittle Tests").

Fix without touching the test/oracle: make the contract **discoverable through the
investigation** the task is already about. `apex_to_clones.py --spec <overlay.json>` merges a
realistic on-call handoff (a tech-lead **ticket comment** naming the file, symbols/signatures,
and behavior, plus a corroborating slack line) into the seeds. The agent finds it via
`linear issue view <ISSUE> --comments`.

Add a spec when a task's `test.patch` pins an interface a behavioral fix can't infer — either
new private symbols (`grep -E "import .*_[A-Z]" test.patch`) or new required call signatures
(`grep -E "func \(|\w+\(" test.patch` vs the pre-fix repo). Purely behavioral tests need none.
NOTE: the **exact** APEX tasks ship the detailed problem statement as the prompt (it already
names the files/messages/behaviors), so in practice the pilots passed **without** a spec — only
reach for `--spec` if a run shows a correct-but-different fix being graded 0.

## Exact APEX tasks (build-time fetch)

The exact mercor/APEX-SWE tasks have **no `base_commit`** — each vendors a full `repo/`
snapshot plus a 16–20 MB git-LFS Matrix chat scrape and a full GitHub issue dump. To keep
our git light, these are **fetched from the public dataset at build**, not committed:

- **repo/** — the task `Dockerfile` runs `huggingface_hub.snapshot_download(... allow_patterns=["<task>/repo/**"])` and builds it (no `base_commit` needed).
- **data → seeds** — a `seed/` init service (compose) fetches `<task>/data/**` from HF and runs
  `apex_to_clones.py` into named volumes (`tvseed`/`slackseed`/`gaugeseed`) the sidecars mount.
  The converter auto-detects the real APEX formats: full GitHub `issues.json` (→ a tracker the
  agent **searches**, not "issue mine"); the chat export, which **varies per task** — Matrix
  (paperless) or Discord (bor) — both flattened to `{channel,author,content,timestamp}`; and raw
  `data/loki/*.log` (Django, geth, …) parsed into gauge entries with `{service,level}` labels.
- **golden.patch / test.patch / test_metadata.json** are small and committed; grading parses the
  exact F2P/P2P node ids and runs the upstream test command. golden = product-only, test = tests-only.

Only `solution/`, `tests/`, `environment/` (Dockerfile, compose, seed/) and `task.toml` live in
git. See `tasks/paperless-ngx-10555/` as the reference.

## Per-task local gate (before Oddish)

1. **Converter fidelity**: run `apex_to_clones.py` on the task's data; confirm issues, chat,
   and log lines are all present in the generated seeds.
2. **Patches apply**: `git init` the fetched `repo/` snapshot, `git apply golden.patch` then
   `git apply test.patch` — both must be clean (golden = product-only, test = tests-only).
3. **oracle=1 / nop=0 repro** (cheap, native arch — don't emulate): in the repo's language
   base image with golden+test applied, run the verifier's exact test command and parsing.
   - paperless: `python -m pytest <files> -o addopts= -p no:cacheprovider -p no:xdist` → 56 pass.
   - bor: `go test <pkgs> -run "^(<tops>)$" -v -timeout 30m` → 437/437 `--- PASS:`.
   Then revert the product files (keep test.patch) and re-run → the F2P tests fail (nop=0).
4. **Flakiness pre-check (REQUIRED — reject non-deterministic tasks).** Re-run the oracle
   test suite with `-count=3` (Go) / `--count 3` or 3 repeats (pytest). If *any* repeat shows a
   `--- FAIL:` / failed required test, the task's oracle is non-deterministic → **do not ship it.**
   This is how op-geth-655 was caught: `TestDAFilters` uses `t.Parallel()` + async
   `buildPayload().WaitFull()` with an exact tx-count assert — it passed unloaded (arm64) and
   failed under load (oddish amd64). Such tasks waste oddish runs and corrupt grading.
5. **Oddish**: run with oracle/nop + ≥1 model; confirm oracle=1, nop=0, agents produce
   real trajectories that exercise `linear`/`slack`/`gcx`.

### Determinism triage (pick deterministic tasks up front)
Prefer tasks whose F2P tests are pure logic / data-structure / config (e.g. bor `./params`,
gossamer `./dot/parachain/types`, paperless API-validation). **Avoid** test packages built around
concurrency/async/timing — they tend to flake under load:
- miner / payload-building (`buildPayload`, `WaitFull`, exact tx counts) — op-geth.
- parachain `statement-distribution` / `availability-distribution` — gossamer networking subsystems.
- anything with `t.Parallel()` + timers/goroutines + exact-count or ordering assertions.
A quick scan of `test.patch` for `t.Parallel`, `time.`, `go func`, `chan ` flags candidates to
pre-check (step 4) harder or skip.

## Batching the remaining ~24 Observability tasks

Both pilots (paperless = Python/Django, bor = Go/go-ethereum) are proven, so the per-task work
is now mostly filling knobs. For each task, copy `tasks/paperless-ngx-10555/` (Python; for a Go
task use the same shape with a `go build`/`go test` Dockerfile + verifier) and set:

- **Dockerfile**: language base image + repo build (`uv sync` vs `go mod download && go build`),
  and `ARG APEX_TASK=Observability/<task-dir>`.
- **environment/seed/**: reuse verbatim (the seed image + `apex_to_clones.py` are task-agnostic);
  set `APEX_TASK` / `APEX_SERVICE` / `APEX_KEY` in `docker-compose.yaml`'s `apex-seed` block.
- **instruction.md**: the APEX `task.yaml` instruction (detailed bug spec) with the tools
  section pointed at `gcx`/`linear`/`slack`.
- **tests/run_verifier.sh**: run the upstream `test_command` and grade the exact F2P/P2P ids
  (pytest `--- ... PASSED` or go `--- PASS:`); `solution/solve.sh` applies golden.patch.
- **task.toml**: schema 1.2; `[[environment.mcp_servers]]` slack + grafana.

### Lessons baked in (gotchas that cost a run each)
- **Verifier env ≠ agent env.** The verifier step runs with a stripped PATH. Toolchains off the
  default PATH must be exported in `run_verifier.sh` (Go: `export PATH=/usr/local/go/bin:$PATH`);
  set `[verifier] user = "root"` so it can read the build's module/cache. (Python `python3` is
  already on PATH, so paperless needed none.)
- **Repo test harness defaults can break collection.** paperless's pytest `addopts` (coverage +
  xdist `-n auto`) crashed workers → "no tests ran"; override with `-o addopts= -p no:xdist`.
- **Large-repo HF fetch hits 429s.** `huggingface_hub` auto-retries (slow); set `HF_TOKEN` in the
  build env for big repos (go-ethereum) to raise the rate limit.
- **golden vs test patches are disjoint** (product-only vs tests-only) — apply golden in the
  oracle, test.patch in the verifier; no conflict.

### Running with cursor
The GitHub `/oddish` workflow's `validate-agents` gate has no Cursor provider (`cursor/composer`
400s as openai). Run via the **oddish CLI directly** instead — it accepts cursor:
`oddish run <task-dir> -c sweep.yaml --background` with a sweep listing oracle/nop/gemini/cursor.

## Clone tool surface (agent)

- Issue tracker: `linear` / `jira` CLIs (`WORLD_ISSUES_*`, `PLANE_BASE_URL`).
- Chat: `slack` CLI + `slack-mcp` MCP (`SLACK_API_URL`, `SLACK_BOT_TOKEN`).
- Observability: `gcx` CLI + `mcp-grafana` MCP (`GRAFANA_URL`, `GRAFANA_TOKEN`).
  Do NOT ship `gaugectl` (admin) into the agent image.
