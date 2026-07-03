# platform/ — the reusable Dokku deploy plane

A drop-in Dokku service + provisioning scripts that turn any live-deployment
eval task into: **agent deploys/reconfigures a real app on a real PaaS, verifier
grades behavior under load.** Socket-sibling mode, proven in `../README.md`
(spike step 0). arm64 Docker Desktop confirmed.

## Files
| File | Role |
|---|---|
| `dokku-service.yaml.snippet` | The `dokku:` service block to paste into a task compose (image `dokku/dokku:0.35.18`, hostname `dokku`, socket mount, per-task state under `/var/lib/dokku-${COMPOSE_PROJECT_NAME}`, no published ports — everything over the task network). |
| `provision-gitsync.sh` | **Recommended provisioner.** Drives dokku entirely via `docker exec` (operator surface). Deploys with `dokku git:sync --build` from a repo path *inside* the dokku container — no SSH, no published ports. Waits for dokku, `events:on`, `ssh-keys:add agent`, `apps:create`, `config:set` (arm fault), `network:set attach-post-create` (auto-discovers the task network), git:sync deploy, waits for health on `<app>.web.1:<port>`. Idempotent. |
| `provision.sh` | Alternative provisioner (coexists). Same setup, but deploys via host-side `git push` over a published SSH port, and can provision a Postgres. Useful when the setup context is the host rather than a sibling. |
| `smoke-compose.yaml` | Self-contained smoke stack (dokku + postgres:16 + python probe), shaped like a task compose. |
| `smoke.sh` | End-to-end proof: compose up → provision+deploy the vendored SUT with the FAULTY env → prove healthy on the direct container-name path, API round-trip, concurrent-load degradation, then the `ssh config:set` fix + redeploy → healthy. Writes `SMOKE-RESULTS.md`. Cleans up (SMOKE_KEEP=1 to keep). |
| `agent_key` / `agent_key.pub` | A sample agent keypair (for local runs; tasks generate their own). |

## How a task includes the plane
1. Paste the `dokku:` service (and set `SUT_REPO_DIR`, `AGENT_PUBKEY`) from
   `dokku-service.yaml.snippet` into the task `docker-compose.yaml`, alongside a
   Postgres, an `otel-collector`, and the agent/verifier sidecar.
2. After `docker compose up -d`, run **`provision-gitsync.sh`** from setup:

   ```sh
   platform/provision-gitsync.sh \
     --dokku-container <proj>-dokku-1 \
     --app conduit \
     --config "DATABASE_URL=postgresql://conduit:conduit@postgres:5432/conduit \
               SECRET_KEY=<secret> \
               WEB_CONCURRENCY=1 \                 # the P4 fault (faulty=1)
               MAX_CONNECTIONS_COUNT=10 MIN_CONNECTIONS_COUNT=5 \
               OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318 \
               OTEL_SERVICE_NAME=conduit OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf" \
     --port 8000 --health-path /api/tags
   ```

   After this the app is live and reachable from any sibling at
   **`conduit.web.1:8000`** (container-name path — the nginx vhost proxy is NOT
   used). The fault is armed (`WEB_CONCURRENCY=1`).

### Key detail: `attach-post-create`
Provisioning runs `dokku network:set <app> attach-post-create <net>` so every
app container dokku creates joins the task network. Without it the app lands only
on dokku's own bridge and siblings can't reach it by name.

## The agent surface
The agent operates dokku over SSH (its key authorized as `agent`). From a sibling
on the task network:

```sh
ssh dokku@dokku config:show conduit
ssh dokku@dokku config:set conduit WEB_CONCURRENCY=4   # the remediation (redeploy)
ssh dokku@dokku ps:report conduit
ssh dokku@dokku logs conduit
```

## The verifier's audit hook
Provisioning runs `dokku events:on`, so `../verifier/soak.py` (and any grader)
can read a tamper-evident audit trail (it even records the agent key fingerprint
on each deploy) plus config/state:

```sh
docker exec <proj>-dokku-1 dokku events            # config-set, deploy, scale...
docker exec <proj>-dokku-1 dokku config:show conduit   # did they set WEB_CONCURRENCY=4?
docker exec <proj>-dokku-1 dokku ps:report conduit
```

The verifier's *primary* signal is behavioral (soak under load, check p95/p99 +
error rate against the fault headroom in `../sut-conduit/otel-wrap/README.md`);
`dokku events`/`config:show` corroborate the fix was a real config change.

## Notes for task compose / collector wiring
- The SUT (see `../sut-conduit/`) exports OTLP/protobuf to
  `http://otel-collector:4318`. Put an `otel-collector` on the task network; it
  re-encodes to OTLP-JSON for the logfire clone (the app never emits JSON). For a
  collector-less smoke, set `OTEL_SDK_DISABLED=true`.
- Postgres: run it as a plain compose service (`postgresql://...@postgres:5432/...`).
  On Docker Desktop the dokku-postgres *plugin* fails (host bind-mount not shared:
  `mounts denied`), so use a compose Postgres; the plugin path works on native Linux.
