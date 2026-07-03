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
