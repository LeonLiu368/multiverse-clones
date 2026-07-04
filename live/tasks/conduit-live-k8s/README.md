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
at boot. They are **baked into the k3s image** (`k3s/Dockerfile` COPYs
`k3s/manifests/*.yaml` there). All workloads are in the `conduit` namespace:

| Manifest | Workload |
|---|---|
| `00-namespace.yaml` | namespace `conduit` |
| `10-postgres.yaml` | `postgres:16` Deployment + in-cluster Service `postgres:5432` |
| `20-logfire.yaml` | logfire clone Deployment (records from a ConfigMap mount) + **NodePort 30080** Service; live OTLP-JSON ingest + `/v2/query` |
| `30-otel-collector.yaml` | collector Deployment (config from a ConfigMap) + Service `otel-collector:4318`; OTLP/protobuf in → OTLP/HTTP **JSON** out to `http://logfire:80`, `compression: none`, Bearer write token |
| `40-conduit.yaml` | conduit SUT Deployment (**`WEB_CONCURRENCY=1` — the fault**) + **NodePort 30800** Service |
| `50-conduit-seed.yaml` | a Job that seeds 3 users / 6 articles + the fixed `soakfixed` login user (seed.py mounted from a ConfigMap; runs on the conduit-otel image as a Python runtime) |

The one telemetry hop that matters (unchanged from the Dokku task): the clone's
stdlib ingest reads the body as plain JSON, so the collector's `otlphttp` exporter
must set **`compression: none`** (its default gzip makes `/v1/traces` 400). With
that, `OTEL_SERVICE_NAME=conduit` lands as `service_name='conduit'` rows carrying
`duration`, `span_name`, `http_route`, `http_method`, `http_response_status_code`.

## How images get into k3s (the one real wrinkle — solved: **Option 1, airgap-bake**)

k3s uses **containerd, not docker**, so Oddish's `--registry-login` (a `docker
login`) does **not** authenticate k3s's image pulls. We avoid all runtime registry
auth by **airgap-baking**: every workload image is placed as a tar in
`/var/lib/rancher/k3s/agent/images/*.tar`, which k3s auto-imports into containerd
at startup. Every workload sets `imagePullPolicy: Never`, so no registry is ever
contacted.

- `environment/k3s/bake-images.sh` (run before `docker compose build k3s`):
  1. builds the `conduit-otel` SUT image (vendored `sut-src/app/` + `otel-wrap/`
     overlay) with `--provenance=false` (single-arch docker manifest, which k3s's
     airgap importer handles cleanly), and
  2. `docker save`s the 4 workload images — `postgres:16`,
     `otel/opentelemetry-collector-contrib:0.116.1`, the **private**
     `ghcr.io/abundant-ai/logfire-service:latest`, and `conduit-otel:latest` —
     into `k3s/airgap/*.tar` (gitignored; ~450MB).
- `environment/k3s/Dockerfile` COPYs `k3s/airgap/*.tar` into the airgap dir and
  `k3s/manifests/*.yaml` into the server-manifests dir.

**Confirmed locally:** after boot, all three image-pulling Deployments
(postgres, logfire, conduit) roll out from `imagePullPolicy: Never` with no
`ErrImagePull` — i.e. the airgap import populated containerd. (The collector too.)

### On Oddish
- The private `logfire-service` image and whatever registry the SUT is pushed to
  are already pulled locally by Harbor's `--registry-login` **before** the build,
  so `docker save` in `bake-images.sh` finds them exactly as it does locally. No
  runtime auth, no public-flip needed with this option.
- If a future harness cannot run `bake-images.sh` as a pre-build step, the
  fallback (Option 2 in the plan) is to make `logfire-service` + the SUT image
  **public** on ghcr and drop `imagePullPolicy: Never` so k3s pulls them (public →
  no auth). That is a manual package-visibility UI flip; not needed for the baked
  path.
- **Resource needs:** k3s + 5 in-cluster workloads. `task.toml` requests 8 cpu /
  16 GB / 40 GB storage (same as the Dokku task). The `k3s` container must be
  `privileged: true` (embedded containerd needs its own namespaces/cgroups — this
  is **not** a docker.sock share).

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

## Measured nop vs oracle (local, arm64 Docker Desktop)

Two-service compose up; k3s healthy in ~6s; all in-cluster workloads Running;
`logfire query` returns live `service_name='conduit'` rows (680 spans seen);
soak drives load at the conduit NodePort.

| Scenario | WEB_CONCURRENCY | overall goodput | overall error_rate | overall p95 | reward |
|---|---|---|---|---|---|
| **NOP** (faulty, no fix) | 1 | 0.040 | 0.961 | ~1510 ms (timeouts) | **0.0** |
| **ORACLE** ×3 (solve.sh fix) | 4 | 1.000 | 0.000 | ~377–402 ms | **1.0, 1.0, 1.0** |

NOP fails BOTH goodput and error_rate gates, per-driver AND overall — a wide,
non-marginal margin. ORACLE is stable ×3. The oracle each run: `logfire query`
diagnoses the single-service latency saturation (all latency on `conduit`, spans in
the multi-second range under load) → `kubectl -n conduit set env deploy/conduit
WEB_CONCURRENCY=4` → `rollout status` → writes `findings.json`.

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

## Local validation

`./validate_local.sh` bakes the airgap images, brings the two-service stack up,
waits for the in-cluster workloads + seed Job, confirms live spans reach logfire,
then runs NOP (faulty → reward 0) and ORACLE (`solution/solve.sh` → reward 1,
repeated ×3). `KEEP=1` leaves the stack up; `SKIP_BAKE=1` reuses existing tars.
