# live/ — live-deployment eval infrastructure

Live tasks = a real OSS app (SUT) deployed on **Dokku** (the deploy plane), telemetry via
**otel-collector → our logfire clone** (live OTLP ingest), graded by a **soak verifier**
(behavior under load, post-agent). See the approved plan; primitives P1-P4.

## Spike results (2026-07-03, local Docker Desktop arm64) — step 0, PASSED

Mode: **socket-sibling** (`/var/run/docker.sock` mounted into the `dokku/dokku:0.35.18`
container; app containers land on the same dockerd) + `dokku network:set <app>
attach-post-create <compose-network>` so app containers join the task network.

| Step | Wall time | Notes |
|---|---|---|
| compose up (incl. image pull) | 74s | dokku image ~cached afterwards |
| dokku init after start | ~1s-40s | ready when `dokku version` answers |
| provision (ssh-keys:add, apps:create, config:set, network:set) | ~5s | via `docker exec` (operator) |
| `git push` Dockerfile deploy | **38s** | the Level-2 agent surface |
| `config:set KEY=VAL` live redeploy (via SSH) | **30s** | the MVP remediation surface |

Verified: sibling → app **direct by container name** (`echo.web.1:5000`) before AND after
redeploy; app outbound → sibling (the app→collector path); faulty env visible pre-fix,
corrected env post-fix. The dokku nginx vhost proxy path times out (nginx targets the app's
`bridge` IP; the dokku container isn't on `bridge`) — **not needed**: loadgen/verifier/agent
use the direct container-name path.

Agent surface (proven): `ssh dokku@dokku <cmd>` (key provisioned via `dokku ssh-keys:add`)
— `config:set`, `config:get`, `ps:report`, `logs`, and `git push dokku@dokku:app` deploys.
Enable `dokku events:on` during provisioning for the verifier's audit trail.

Fallback ladder (unused): docker-socket-proxy → custom deployd.

## Re-platform: Dokku → self-contained k3s (2026-07-05)

The Dokku plane is **socket-sibling** (mounts `/var/run/docker.sock`). That is incompatible
with Harbor's Daytona DinD runner: `dind_compose.py::_fetch_file_from_host` and the nested
dockerd path fail when the task also mounts the host socket, and some Daytona sandboxes can't
start a nested dockerd at all (`/sys/fs/cgroup: read-only`). So the live task was re-platformed
onto a **self-contained k3s** plane that mounts **no** docker socket: one privileged `k3s`
container runs its own embedded containerd, and the whole stack (postgres, logfire clone,
otel-collector, the conduit SUT + a seed Job) runs as k8s manifests baked into the image and
applied at boot. Workload images are pulled at runtime from PUBLIC registries (an airgap-tar
bake produced a 422 MB task upload that S3 rejected — `EntityTooLarge`). Agent remediates via
`kubectl -n conduit set env deploy/conduit ...`; the task dir is `live/tasks/conduit-live-k8s/`
(the Dokku version `live/tasks/conduit-degraded-writes/` is kept intact).

Local (Docker Desktop): k3s boots to READY in ~5–32 s, `kubectl set env` rolls out in ~1 s,
NodePorts reachable from the `main` sibling; **nop=0.0 / oracle=1.0 ×3**. The task logic,
telemetry path, and soak grading are correct.

## Oddish result — GREEN: nop=0 / oracle=1 (exp `3d288875`, 2026-07-09)

Final state: **nop=0.0, oracle=1.0, oracle=1.0 on Oddish, first attempt, zero retries,
~6 min/trial** (experiment `eager-quartz-519p` / `3d288875`).

### First model trial: gemini-3.1-pro-preview = 1.0 (good success, exp `4e84404e`)

Verified via trajectory forensics (80 tool calls), not just the grade: explored the cluster,
read the logfire schema, ran real distributed-tracing queries (per-route duration aggregates,
trace-id drill-downs into the slow POST /api/articles chain), wrote its own concurrent load
generators to reproduce the degradation, ran controlled knob experiments (WEB_CONCURRENCY x
MAX_CONNECTIONS_COUNT sweeps, including a deliberate WEB_CONCURRENCY=1/pool=100 control),
inspected postgres + pod resources, settled on WEB_CONCURRENCY=8 (a valid fix different from
the oracle's 4 — exactly what behavior-over-time grading is for), and filed a findings.json
naming the saturation mechanism. No verifier tampering; remediation via the sanctioned kubectl
surface only. discord-recall re-confirmed 1.0 in the same experiment (agent `gemini-cli`,
model `google/gemini-3.1-pro-preview` — note the agent NAME is `gemini-cli`; `gemini` fails
at `starting` with empty logs).

### The real root cause (and the two bugs that masked it)

**Root cause: `ghcr.io/abundant-ai/conduit-otel:latest` was a single-arch linux/arm64
image** (publish-sut.sh defaulted `PLATFORM=linux/arm64`, pushed from a Mac). Daytona
sandboxes are amd64: the SUT container crashed instantly (exec format error) →
CrashLoopBackOff on every sandbox, while running natively on arm64 dev machines — a
perfect works-locally/dies-in-cloud trap. Fixed: publish-sut.sh now builds+pushes
`linux/amd64,linux/arm64` via buildx (like the CI-built logfire-service always did).

Two masking layers made this take five Oddish iterations to see:
1. **k3s couldn't boot at all on many sandboxes** (cgroup v2 nesting: the container's
   root cgroup held our PIDs, so kubelet couldn't create delegated child cgroups —
   pods are exactly that). Fixed in k3s-entrypoint.sh with the standard k3d dance
   (evacuate PIDs to /init + enable subtree_control). Until then, most attempts died
   before ever reaching the CrashLoop.
2. **The old verifier graded dead environments 0.0** ("never crash without a reward"
   wrote reward.txt=0.0 with infra_error:true — but the harness scrapes any reward
   file as a TERMINAL grade). Early "nop=0.0 (real soak)" results were therefore
   FALSE grades on dead targets; the "host variance" theory they supported was wrong.
   Fixed contract: infra failure → result.json only (debug), NO reward file, exit 3 →
   `RewardFileNotFoundError` → retryable trial error. Model trials can no longer be
   unfairly zeroed by a dead environment.

What finally cut through: **cluster-state diagnostics in the verifier** (pods -A,
describe non-ready, events — captured in test-stdout.txt even on infra exits). One
look showed postgres/logfire/otel/coredns Running and only conduit crash-looping with
successful pulls; three commands later the arm64 manifest was confirmed.

Robustness fixes that remain in place from the investigation (each independently
sound): boot-safe node-IP pin + kubeconfig rewrite (Daytona multi-homing),
`--flannel-backend=host-gw` (no vxlan kernel-module dependency), docker.io pulls via
mirror.gcr.io with fallback (shared-egress-IP rate limits), k3s boot log tee'd to the
shared volume, cluster-state dumps in test.sh + solve.sh failure paths.

**Debugging lesson for future live tasks:** when something "works locally but fails
in the cloud", check image architectures FIRST (`docker manifest inspect`) — and make
sure the verifier can never convert an infra failure into a terminal grade, or every
later diagnosis inherits the false data.
