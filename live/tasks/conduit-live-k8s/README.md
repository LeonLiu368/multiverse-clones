# live/tasks/conduit-live-k8s

A **live-deployment observability + remediation** eval task, on a **SELF-CONTAINED
k3s plane**. This is the re-platform of `live/tasks/conduit-degraded-writes` off the
Dokku deploy plane (which fails on Oddish/Daytona: its Dokku is *socket-sibling* —
it mounts the sandbox `/var/run/docker.sock` and spawns sibling containers, which
broke Harbor's DinD-compose file-transfer to `main` and hit nested-dockerd cgroup
failures). The fix is a **k3s cluster with its own embedded containerd — NO host
docker.sock anywhere** (the mechanism proven in `live/spike-k3s/`).

Same task, same fault, same calibrated soak — only the deploy plane changed:
Dokku SSH → `kubectl`.

Conduit (a RealWorld FastAPI + Postgres service) runs as a k8s Deployment inside
k3s with a config-driven fault: a **single uvicorn worker** (`WEB_CONCURRENCY=1`),
so under concurrent load the CPU-bound request path (bcrypt logins) serializes on
one asyncio event loop and article writes / logins saturate. The agent must:

1. **Diagnose from live telemetry** — spans stream `conduit → otel-collector →
   logfire clone` (all in-cluster); the agent queries them with `logfire query`
   (SQL over a `records` table) at the logfire NodePort.
2. **Remediate the live deployment** via `kubectl`
   (`kubectl -n conduit set env deploy/conduit WEB_CONCURRENCY=4` → rollout).
3. **Write `/workspace/findings.json`** naming the failing component + mechanism.

Graded by a post-agent **soak** (drives concurrent load at the conduit NodePort,
checks the deployment now holds up) + a findings mechanism gate. **nop=0, oracle=1.**

## The 2-service compose (`environment/docker-compose.yaml`)

EXACTLY TWO services — and **no `docker.sock` mount anywhere** (the whole point):

| Service | Role |
|---|---|
| `k3s` | one **privileged** container running `k3s server --disable traefik --disable metrics-server --snapshotter native --tls-san k3s`, with `tmpfs: [/run, /var/run]`. Its own embedded containerd — NOT a shared host daemon. The whole stack runs as k8s manifests INSIDE it. Kubeconfig is written to a shared `kube` volume (`K3S_KUBECONFIG_OUTPUT`, mode 666). Exposes NodePorts `:30080` (logfire) and `:30800` (conduit) on the k3s container. |
| `main` | the agent: `python:3.12-slim` + `kubectl` + `logfire` CLI/MCP (client-only, **no `server.py`**) + httpx/curl/jq. Its entrypoint copies the kubeconfig from the shared volume and **rewrites the apiserver `https://127.0.0.1:6443 → https://k3s:6443`** so a sibling reaches the cluster, then waits for k3s Ready + conduit healthy + live spans before handoff. **No answer material.** |

`main` `depends_on: k3s (service_healthy)`. No explicit `networks:` — Harbor puts
both on one default network, so `main` reaches everything at hostname `k3s`.

## How the stack is manifested (inside k3s)

k3s auto-applies every manifest dropped in `/var/lib/rancher/k3s/server/manifests/`
at boot. Only the manifests are **baked into the k3s image** (`k3s/Dockerfile` COPYs
`k3s/manifests/*.yaml` there — that is the k3s image's *entire* payload over the
`rancher/k3s` base; it stays 286MB, no bigger than the base). All workloads are in
the `conduit` namespace:

| Manifest | Workload |
|---|---|
| `00-namespace.yaml` | namespace `conduit` |
| `10-postgres.yaml` | `postgres:16` Deployment + in-cluster Service `postgres:5432` |
| `20-logfire.yaml` | logfire clone Deployment (records from a ConfigMap mount) + **NodePort 30080** Service; live OTLP-JSON ingest + `/v2/query` |
| `30-otel-collector.yaml` | collector Deployment (config from a ConfigMap) + Service `otel-collector:4318`; OTLP/protobuf in → OTLP/HTTP **JSON** out to `http://logfire:80`, `compression: none`, Bearer write token |
| `40-conduit.yaml` | conduit SUT Deployment (**`WEB_CONCURRENCY=1` — the fault**) + **NodePort 30800** Service |
| `50-conduit-seed.yaml` | a Job that seeds 3 users / 6 articles + the fixed `soakfixed` login user (seed.py mounted from a ConfigMap; runs on the public `conduit-otel` image as a Python runtime) |

The one telemetry hop that matters (unchanged from the Dokku task): the clone's
stdlib ingest reads the body as plain JSON, so the collector's `otlphttp` exporter
must set **`compression: none`** (its default gzip makes `/v1/traces` 400). With
that, `OTEL_SERVICE_NAME=conduit` lands as `service_name='conduit'` rows carrying
`duration`, `span_name`, `http_route`, `http_method`, `http_response_status_code`.

## How images get into k3s — **k3s pulls PUBLIC images at runtime** (`IfNotPresent`)

k3s uses **containerd, not docker**, so Oddish's `--registry-login` (a `docker
login`) does **not** authenticate k3s's image pulls. The strategy is therefore:
**all workload images are PUBLIC, and k3s's containerd pulls them at runtime** — no
registry auth needed. Every workload sets `imagePullPolicy: IfNotPresent` (reuse a
locally-present image, else pull).

Image refs:

| Image | Registry | Status |
|---|---|---|
| `docker.io/library/postgres:16` | Docker Hub | already public |
| `docker.io/otel/opentelemetry-collector-contrib:0.116.1` | Docker Hub | already public |
| `ghcr.io/abundant-ai/logfire-service:latest` | ghcr | **needs public-flip** |
| `ghcr.io/abundant-ai/conduit-otel:latest` | ghcr | **needs public-flip** — the SUT (published this rework, `sha256:29401be3…`) |

### Two ghcr packages must be flipped PUBLIC (manual UI step, one-time)
`ghcr.io/abundant-ai/logfire-service` and `ghcr.io/abundant-ai/conduit-otel`. Until
they are public, k3s cannot pull them on Oddish. (Local runs sidestep this — see
below.) The two Docker Hub images are already public.

### The SUT image (`conduit-otel`)
Published this rework to `ghcr.io/abundant-ai/conduit-otel:latest` from the OTel
overlay (`sut-src/otel-wrap/`) over the vendored RealWorld app. Because it's now a
published image, **the vendored app source is no longer carried in this task dir**
(the image carries it) — provenance + the rebuild recipe are in
`sut-src/MANIFEST.json` and `sut-src/otel-wrap/publish-sut.sh` (an OPTIONAL
maintenance script; the task's `docker compose build` never builds the SUT).

### Why the previous airgap-bake is GONE
An earlier revision airgap-baked all 4 images into the k3s image
(`/var/lib/rancher/k3s/agent/images/*.tar`). That produced a **422MB task upload
that Oddish's S3 rejected — EntityTooLarge**, and it could not use
`--registry-login` for k3s anyway. Runtime public-pull removes both problems and
shrinks the upload to ~117KB.

### Local runs before the public flip
`validate_local.sh` imports the workload images into k3s's containerd
(`docker save <img> | k3s-container ctr -n k8s.io images import -`) right after boot,
so `IfNotPresent` finds them without any registry pull. This writes nothing to the
tree and is NOT in the task Dockerfile. On Oddish (packages public) k3s just pulls
them itself — no import step.

### Resource needs
k3s + 5 in-cluster workloads. `task.toml` requests 8 cpu / 16 GB / 40 GB storage
(same as the Dokku task). The `k3s` container must be `privileged: true` (embedded
containerd needs its own namespaces/cgroups — this is **not** a docker.sock share).

## The agent surface

- **Diagnose:** `logfire query "…"` (and `logfire-mcp`) → `http://k3s:30080/v2/query`
  with the read token. Client-only; the corpus is not on disk in `main`.
- **Remediate:** `kubectl` against `https://k3s:6443` (kubeconfig from the shared
  volume, server rewritten). E.g. `kubectl -n conduit get deploy/conduit`,
  `kubectl -n conduit set env deploy/conduit WEB_CONCURRENCY=4`,
  `kubectl -n conduit rollout status deploy/conduit`.
- The SUT is reachable at `http://k3s:30800` (NodePort).

## The fault + fix

- **Fault (baked into `40-conduit.yaml`):** `WEB_CONCURRENCY=1` — one uvicorn worker.
- **Fix (oracle / agent):** `kubectl -n conduit set env deploy/conduit WEB_CONCURRENCY=4`
  → rollout (4 workers). NOT named in the instruction or the `main` image.

Why this knob (measured, see `sut-src/otel-wrap/README.md`): the app is fully async
and local queries are sub-ms, so the single Python event loop — not the asyncpg pool
— is the bottleneck. Real traffic includes session churn: every login does a
passlib/bcrypt verify (~265ms of pure CPU) that blocks the whole event loop of a
single worker.

## Calibrated soak (`tests/soak_config.json`) — reused as-is, no re-tune

Target rewritten to the NodePort `http://k3s:30800`; all calibration values kept:
`rps=8`, `workers=24`, `request_timeout_s=1.5`, `goodput_min=0.80`,
`error_rate_max=0.15`, `warmup_s=12`, `soak_s=60`. Two flows (weight 1.0 each):
`write_readback` (POST `/api/articles` + read-back by slug) and `login_churn`
(POST `/api/users/login` per request — the bcrypt CPU that blocks the single event
loop). Findings gate (`mechanism_regexes`): must match
`(worker|concurren|event.?loop)` AND `(bcrypt|cpu|serial|saturat|block|queue)`.

## Measured nop vs oracle (local, arm64 Docker Desktop) — re-verified after the rework

Two-service compose up; k3s healthy in ~6s; all 4 in-cluster workloads Running
(conduit + logfire via containerd-imported public images, postgres + otel-collector
via runtime pull); `logfire query` returns live `service_name='conduit'` rows
(800–950 spans seen); soak drives load at the conduit NodePort. **Two consecutive
full `validate_local.sh` runs both PASS (nop=0, oracle=1 ×3).**

| Scenario | WEB_CONCURRENCY | overall goodput | overall error_rate | overall p95 | reward |
|---|---|---|---|---|---|
| **NOP** (faulty, no fix) | 1 | 0.62 (login_churn driver **0.00**) | low | ~360 ms + queue | **0.0** |
| **ORACLE** ×3 (solve.sh fix) | 4 | 1.000 | 0.000 | ~329–402 ms | **1.0, 1.0, 1.0** |

NOP fails the goodput gate decisively: the `login_churn` driver (bcrypt on the
single event loop) scores **0.00 goodput** — 0/262 logins complete within the SLO —
so overall goodput (0.62) is well under the 0.80 gate. ORACLE is stable ×3 (goodput
1.0, error 0.0). The oracle each run: `logfire query` diagnoses the single-service
latency saturation (all latency on `conduit`, spans in the multi-second range under
load) → `kubectl -n conduit set env deploy/conduit WEB_CONCURRENCY=4` → waits for
the rollout to FULLY converge → writes `findings.json`.

### Rollout-convergence hardening (learned during re-verify)
`kubectl rollout status` returns when the Deployment reports complete, but the old
single-worker pod (and the Service endpoint routing to it) can linger for a beat.
An early oracle run measured that stale window and failed. `solution/solve.sh` (and
the validator's re-arm) now wait until exactly **one ReplicaSet is active and one
pod is Ready** (old RS scaled to 0), plus a short endpoint-settle, before load hits
the NodePort. With that, oracle is stable ×3 across repeated runs.

## Anti-leak (verified)

- `instruction.md`: no `WEB_CONCURRENCY`/`worker`/`bcrypt`/`=4` (only the generic
  "what serializes/saturates" phrasing in the findings-schema placeholder).
- `main` image: no answer material under `/opt` or `/usr/local/bin`; **no
  `server.py`** (the logfire corpus is not greppable/recomputable in `main`).
- The agent CAN observe `WEB_CONCURRENCY=1` in the live Deployment via `kubectl`
  (the legitimate observable state — the k8s analogue of `dokku config:show`); the
  findings gate still forces naming the *mechanism* (bcrypt/event-loop), so this is
  diagnosis, not a leaked answer.

## Confirmation: NO docker.sock is mounted anywhere

`environment/docker-compose.yaml` has no `/var/run/docker.sock` volume on either
service. Confirmed at runtime: `ls /var/run/docker.sock` inside the `k3s` container
returns "No such file or directory" — k3s runs its own embedded containerd. This is
the entire reason for the re-platform.

## Task upload size

**~117 KB** (manifests + the `main` agent image build context + soak + docs). No
image tars, no vendored app source. This is the fix for the Oddish S3
`EntityTooLarge` rejection the 422MB airgap-baked revision hit.

## Local validation

`./validate_local.sh` imports the workload images into k3s's containerd (so
`IfNotPresent` works before the ghcr packages are public), brings the two-service
stack up, waits for the in-cluster workloads + seed Job, confirms live spans reach
logfire, then runs NOP (faulty → reward 0) and ORACLE (`solution/solve.sh` → reward
1, repeated ×3). `KEEP=1` leaves the stack up.

## Oddish checklist

1. **Flip PUBLIC** the two ghcr packages: `ghcr.io/abundant-ai/logfire-service` and
   `ghcr.io/abundant-ai/conduit-otel` (manual package-visibility UI step). The two
   Docker Hub images are already public.
2. That's it for images — k3s pulls all four at runtime; no `--registry-login`
   needed for k3s (it wouldn't help containerd anyway).
3. `k3s` needs `privileged: true`; resources 8cpu/16GB/40GB.
