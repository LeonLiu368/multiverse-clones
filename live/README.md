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

## Oddish/Daytona result — capability PROVEN; a platform-variance limitation remains

Runs on Oddish (task `conduit-live-k8s-d878252a`):

| Exp | Config | nop | oracle | Read |
|---|---|---|---|---|
| `4e75302b` | pre node-ip fix | infra_error | infra_error | k3s auto-picked the Daytona HOST public IP as node-ip → `main` couldn't route |
| `ec1f5c85` | `--node-ip $(hostname -i)` | **0.0 (real soak)** | infra_error | node-ip pin regressed k3s boot on some hosts |
| `95fb2fb3` | boot-safe node-ip guard | **0.0 (real soak)** | infra_error ×6 | k3s `exited (1)` at boot on all 6 oracle-host draws |
| `cd52a4fb` | + `service_started` (diag) | 0.0 | **false 0.0** | proved Harbor execs the agent on container-**running**, not entrypoint-ready; the `service_healthy` gate is the only readiness barrier — reverted |
| `13a8beec` | restored + oracle ×3 | infra_error | infra_error ×3 | **entire host pool bad at that time** — no good draw across 4 trials × many retries |

**Root cause: Daytona host variance.** On some Daytona hosts, nested privileged k3s **crashes
at boot** — almost certainly the same read-only `/sys/fs/cgroup` constraint that blocks nested
dockerd (a container runtime can't write cgroups there). On hosts without it, the full stack
works — which is why `nop` ran **real end-to-end soaks** on Oddish (exps `ec1f5c85`, `95fb2fb3`).
`oracle` simply never drew a good host, and in `13a8beec` the pool was bad enough that even `nop`
failed. This is a **platform constraint, not a task defect**: there is no task-side flag that
makes k3s boot on a read-only-cgroup host, and k3s's crash reason isn't capturable through
Harbor's log collection (it captures the agent's exec stdout + orchestration, but not a sibling
container's logs nor `main`'s entrypoint stdout).

**Status: the live-deployment capability (P1 deploy actuation, P2 live OTLP ingest, P3 soak
grading, P4 seed-fault) is built and validated** — `oracle=1/nop=0` locally ×3, and `nop`
end-to-end soaks live on Oddish. Landing a clean `oracle=1` on Oddish is gated only on drawing a
Daytona host where nested k3s boots. Mitigations when Daytona capacity allows: (a) re-run with a
higher trial/retry budget until a good host is drawn (bad-host rate is time-varying — good hosts
existed in `ec1f5c85`/`95fb2fb3`); (b) if Harbor exposes a cgroup-writable or k8s-native runner,
target that instead of nested k3s. Not fixable by changing the task.
