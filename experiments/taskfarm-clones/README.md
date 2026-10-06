# taskfarm-clones — taskfarm-e2e tasks on the abundant Slack/Jira clones

Six end-to-end tasks from
[`multiverse-tasks-owen` @ `codex/taskfarm-scout-accepted-wave`](https://github.com/abundant-ai/multiverse-tasks-owen/tree/codex/taskfarm-scout-accepted-wave/taskfarm-e2e-tasks),
re-pointed from the **old `ticketvector-service` + old `slack-service`** to our **new
`jira-gateway` / `slack-gateway` clones** (the two-image + mount + service-DNS isolation model).

**Only the Slack and ticketvector pieces were converted.** The `github` (ghc-service), `sentry`
(sentry-clone-service), `grafana`, `postgres`, the task codebases, and every verifier/oracle script
are untouched.

## What changed (identical transform across all six tasks)

| Piece | Old | New |
|---|---|---|
| Issue-tracker sidecar | `ticketvector-service:main`, `network_mode: service:main` (shares `main`'s netns, binds `127.0.0.1:8765`) | service **`jira`** = `${JIRA_GATEWAY_IMAGE:-ghcr.io/abundant-ai/jira-gateway:empty}`, `hostname: jira`, `/health` healthcheck, **no `network_mode`** — reached at `http://jira:8765` by service-name DNS |
| Per-task tickets | `./data/ticketvector/state.json` mounted into the sidecar | **same mount** (`:ro`) into `jira-gateway:empty` — the gateway serves it over `/rpc` + the `jira` CLI |
| Agent → tracker | `PLANE_BASE_URL=http://127.0.0.1:8765` | `PLANE_BASE_URL=http://jira:8765` + `WORLD_ISSUES_BACKEND=remote`, `WORLD_ISSUES_AGENT_MODE=1`, `WORLD_ISSUES_OUTPUT=json`, `WORLD_ISSUES_DEFAULT_PROJECT=<KEY>`, `depends_on: { jira: service_healthy }` (set in both `Dockerfile` ENV and compose) |
| Verifier → tracker | RPC base `("http://127.0.0.1:8765", "http://main:8765")` | `("http://jira:8765", …)` (kept old bases as fallbacks) |
| Slack sidecar (tbmq only) | `slack-service:latest`, mounts `./data/slack:/data/mattermost` | `${SLACK_GATEWAY_IMAGE:-ghcr.io/abundant-ai/slack-gateway:empty}` — **same mount**; the gateway's boot still imports a legacy `scraped.json` from `/data/mattermost` |

No task **data** needed converting: the Jira `state.json` is the same format ticketvector serves, and
the Slack `scraped.json` is consumed by the gateway's legacy `--scraped` import path at the same
mount point.

## Per-task project keys

`cockroach-*` → `CRDB`, `loki-*` → `LOKI`, `prometheus-*` → `PROMOP`, `tbmq-*` → `TBMQ`,
`tpcc-*` → `MO`.

## Isolation

Ticket/message data lives **only** inside the `jira` / `slack` sidecars (mounted there, never on the
agent's `main` filesystem). The agent reaches them only over HTTP via the `jira` CLI / Slack Web API,
so it can't bypass the tools by reading `state.json` / `scraped.json` off disk.

## Local validation done

Both converted sidecars were smoke-tested standalone against the real task data:
- `jira-gateway:empty` + `cockroach` `state.json` → `/rpc get_issue CRDB-63963` returns the seeded
  issue (state `In Progress`, the pre-agent starting state the verifier transitions from).
- `slack-gateway:empty` + tbmq `scraped.json` → boot logs `IMPORT_OK channels=4 messages=8`;
  `conversations.list` returns the 4 channels and `search.messages?query=mqtt_gap` returns 2 hits.

Full end-to-end `nop=0` / `oracle=1` spans the whole multi-service stack (postgres seed, ghc-service,
sentry, the app build, the deterministic verifier) and is intended to run via the Oddish sweep
(`taskfarm-clones-manifest.yaml`). A cloud run additionally depends on the unchanged
github/sentry/grafana images being pullable.

## Two variants per task — empty ↔ prod-v1 is a ONE-LINE switch

Each of the 6 tasks ships twice. The two composes are **identical except the sidecar image** — the
data mounts are the same path in both variants:

| Variant | sidecar image | jira mount | slack mount (tbmq) | Workspace served |
|---|---|---|---|---|
| `<task>` | `jira-gateway:empty` / `slack-gateway:empty` | `…/state.json:/data/state-overlay.json` | `…/slack-overlay:/data/slack-overlay` | only the task's own data |
| `<task>-prodv1` | `jira-gateway:prod-v1` / `slack-gateway:prod-v1` | **same** | **same** | **prod corpus + task data merged** |

The gateways decide base-vs-overlay by whether the image has a baked corpus, so the **same mount
path** works for both:
- **jira** (`jira-boot.sh`): `:prod-v1` has the baked ENG corpus → the mount at `/data/state-overlay.json`
  is **merged on top**; `:empty` has no corpus → that mount **is** the base. (Boot also normalizes the
  state to a write-faithful shape.)
- **slack** (`slack-boot.sh`): `:prod-v1` has the prebuilt prod DB → `/data/slack-overlay` is layered on
  top; `:empty` imports the same `/data/slack-overlay` export as the base workspace.

So flipping a task between an empty workspace and the prod corpus is just changing the image (or
setting `JIRA_GATEWAY_IMAGE` / `SLACK_GATEWAY_IMAGE`). The prod-v1 sidecars are **pinned by digest**
because the cloud runner caches image tags — a re-pushed tag won't refresh.

The `-prodv1` variants exercise realism/scale: the agent must locate the task's tickets/messages
inside a large real corpus (ENG: 8040 → 8043 issues after merge; slack: 88 → 92 channels). Verified
locally: jira serves both `CRDB-63963` (task) and `ENG-2016` (prod) and the full oracle
`update→comment→update` sequence returns `ok=True`; slack serves `broker-oncall` among the 92 channels.

## How it was converted

Deterministically, by `convert_taskfarm.py` (vendored here) (copies each task dir, rewrites the compose via
PyYAML, the `Dockerfile` ENV and the verifier RPC base via text replacement).
