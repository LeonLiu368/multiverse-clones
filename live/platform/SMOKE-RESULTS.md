# SMOKE-RESULTS — dokku plane + vendored Conduit SUT (measured)

Run: 2026-07-02T18:38:55 · arm64 Docker Desktop ·
stack: `smoke-compose.yaml` (dokku 0.35.18 socket-sibling + postgres:16 + python probe) ·
SUT: vendored `nsidnev/fastapi-realworld-example-app` @ 029eb77 + `otel-wrap/` overlay ·
verdict: **PASS**

## Timings
| Phase | Wall time |
|---|---|
| compose up (dokku+postgres+probe) | 0s |
| probe prep (apt openssh-client) | 8s |
| provision + FAULTY deploy (`git:sync --build`) | 40s |
| fix (`ssh config:set` -> rebuild -> healthy) | 34s |
| faulty load run | 29s |
| fixed load run | 10s |
| **total smoke** | **125s** |

Cold-cache reference (first-ever run on this host): compose up incl. image pulls
~74s; `git:sync --build` deploy ~275s (dominated by the SUT image build: apt gcc
+ pip install incl. compiling asyncpg 0.26 from source on aarch64). Warm-layer
deploys (the numbers above) are ~40s, matching the spike's 38s `git push` deploy.
The `config:set` fix redeploy ranged 30-39s across runs, matching the spike's 30s.

## The fault, measured through dokku (direct container-name path)
Workload: 12 concurrent writers x 20 iterations; each iteration = 1 write
(`POST /api/articles`) + 1 read (`GET /api/articles?limit=20`), plus a login
(bcrypt session churn) every 5th iteration. `livesmoke-conduit.web.1:8000`, probe sibling.

| Config | rps | p50 ms | p95 ms | max ms | errors |
|---|---|---|---|---|---|
| faulty | 23.8 | 163.8 | 2186.8 | 4422.3 | 0/528 |
| fixed | 88.9 | 34.1 | 419.2 | 2000.5 | 0/528 |

Separation: **p95 x5.2**, throughput x3.7. Fault knob:
`WEB_CONCURRENCY` (faulty=1, fix=4) — see `../sut-conduit/otel-wrap/README.md`
for why the originally-hypothesized `MAX_CONNECTIONS_COUNT` pool knob was
measured and rejected.

## Verified along the way
- app healthy on **direct container name** before AND after the fix redeploy
  (the dokku nginx vhost proxy is not used, per the spike)
- login/create-article/read-back API round trip
- agent surface: `ssh dokku@dokku config:set/config:get` with the pre-generated
  agent key (`ssh-keys:add agent`); `config:get WEB_CONCURRENCY=4`
  post-fix; uvicorn logged 4 started worker processes
- deploy path: `dokku git:sync --build` from an in-container local git repo
  (no SSH needed for provisioning)
- `dokku events:on` audit trail tail:

```
2026-07-03T01:38:44.609847+00:00 dokku dokku-event[65412]: INVOKED: certs-force( livesmoke-conduit ) NAME=agent FINGERPRINT=SHA256:mggttKfDpHLclUWb889g+uotx2efAhEHCBMmZoDyJWo DOKKU_PID=36576
2026-07-03T01:38:44.671246+00:00 dokku dokku-event[65519]: INVOKED: proxy-type( livesmoke-conduit ) NAME=agent FINGERPRINT=SHA256:mggttKfDpHLclUWb889g+uotx2efAhEHCBMmZoDyJWo DOKKU_PID=36576
2026-07-03T01:38:44.741722+00:00 dokku dokku-event[65647]: INVOKED: proxy-type( livesmoke-conduit ) NAME=agent FINGERPRINT=SHA256:mggttKfDpHLclUWb889g+uotx2efAhEHCBMmZoDyJWo DOKKU_PID=36576
2026-07-03T01:38:44.799730+00:00 dokku dokku-event[65775]: INVOKED: proxy-type( livesmoke-conduit ) NAME=agent FINGERPRINT=SHA256:mggttKfDpHLclUWb889g+uotx2efAhEHCBMmZoDyJWo DOKKU_PID=36576
2026-07-03T01:38:44.855691+00:00 dokku dokku-event[65904]: INVOKED: proxy-type( livesmoke-conduit ) NAME=agent FINGERPRINT=SHA256:mggttKfDpHLclUWb889g+uotx2efAhEHCBMmZoDyJWo DOKKU_PID=36576
2026-07-03T01:38:44.908509+00:00 dokku dokku-event[66033]: INVOKED: proxy-is-enabled( livesmoke-conduit ) NAME=agent FINGERPRINT=SHA256:mggttKfDpHLclUWb889g+uotx2efAhEHCBMmZoDyJWo DOKKU_PID=36576
```

## OTel
Smoke runs with `OTEL_SDK_DISABLED=true` (no collector in this stack, per plan —
the logfire receiver is wired at task-assembly). Instrumentation itself was
verified separately with a console exporter: FastAPI server spans
(`GET /api/articles`) + asyncpg client spans (19 `SELECT` spans for one list
page — the app's N+1 is visible). Enabling export is pure env:
`OTEL_SDK_DISABLED` off + `OTEL_EXPORTER_OTLP_ENDPOINT=http://<collector>:4318`.
