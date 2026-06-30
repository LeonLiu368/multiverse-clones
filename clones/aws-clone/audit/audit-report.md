# Clone Audit Report — `aws-clone`

- **Audited:** `2026-06-30` (round 2, re-audit after fix pass) · **Auditor:** `clone-audit v1` · **Commit:** `b2b2abd`
- **Fidelity tier (declared / observed):** `T3` (OSS-backed / LocalStack) / `T3`
- **Verdict:** ✅ MEETS STANDARD — *(meets = all gating reqs pass)*
- **Gating score:** `6/6` gating requirement-groups pass (R1 ✅ R2 ✅ R3 ✅ R4 ✅ R5 ✅ R6 ✅).

## TL;DR
Round-1 was 1/6 (R3 no MCP [headline], R2 no prod-v1/baked DB, R1 no bundled task, R4 no COVERAGE, R6
partial). The fix pass closed **every** gating gap and I independently re-ran each one. `aws-clone` is a
T3 LocalStack-backed AWS sidecar: agents drive the **real `aws`/`awslocal` CLI** across 12 services plus
a thin **IAM hybrid shim**. The fix pass added:
- **`aws_clone/mcp/` FastMCP stdio server** (`bin/aws-mcp`) — **starts, lists 26 tools, round-trips tool
  calls**, and is a verified **thin boto3 client** of the same `AWS_ENDPOINT_URL` the CLI uses; live
  CLI↔MCP parity holds (R3, the headline gate — **confirmed**).
- **`Dockerfile.prod-v1`** (corpus baked in, boots mount-free) + **`Dockerfile.empty`** (mount target) —
  tag-only switch (R2.b/j — confirmed by booting both).
- **`oddish/tasks/payment-reconcile/`** with `test.sh`→`reward.txt` + `solution/solve.sh` — **nop=0,
  oracle=1** confirmed (R1).
- **`docs/COVERAGE.md`** 26-row matrix, 12 assessment-grade (R4/R5).
- **`tests/test_mcp_parity.py` + `tests/test_isolation.py` + `tests/test_aws_surface.py`** (R6).

Only a single non-gating P2 remains: two compose self-standup smoke tests race their own `up -d` before
gateway health.

## What it handles well
- **MCP server is real and thin (R3 ✅).** `aws-mcp` (FastMCP/stdio) starts in the agent image, completes
  the JSON-RPC `initialize`+`tools/list` handshake (`serverInfo: abundant-aws-clone`), and lists **26
  tools** (24 agent data-plane + 2 operator). Every tool in `aws_clone/mcp/tools.py` is a boto3 call to
  `AWS_ENDPOINT_URL` (or the admin HTTP client) — **no business logic**, so the CLI and MCP can't drift.
- **Live CLI↔MCP parity.** Against a running gateway, `awslocal` and the matching MCP tool return the
  same data (`acme-payment-exports`, `payment-idempotency`, identical SQS QueueUrls); gated parity pytest
  (s3/dynamodb/sqs) is 3/3; MCP `put_item`→`get_item` round-trips.
- **Baked-DB image trio (R2 ✅).** `:prod-v1` boots **mount-free** in ~64s and serves the baked corpus;
  `:empty` + mount serves the per-task fixture. Switching is the tag alone.
- **Bundled, scorable task (R1 ✅).** `payment-reconcile` is a multi-service observability+devops task;
  nop=0 / oracle=1 measured live (a DynamoDB write→read round-trip read back through the same API).
- **Clean agent/operator boundary + isolation (R2.g, R6.3 ✅).** Agent image carries no `state.json`,
  `import aws_clone.seed` raises `ModuleNotFoundError`, no `seed/`/`admin/` source, answer not greppable —
  while `aws`, `awslocal`, and `aws-mcp` all still load.

## Scorecard

| Req | Area | Result | Evidence | Action item (if not full pass) |
|---|---|---|---|---|
| R1 | Setup & run (Harbor) | **pass** | `payment-reconcile` pair boots (gateway healthy, agent depends_on health, reaches `http://aws:4566`); nop→`reward.txt=0`, oracle→`reward.txt=1` | — |
| R2 | Architecture canon a–g + seeding j–k | **pass** | a–k pass: `:prod-v1` boots mount-free serving baked corpus, `:empty`+mount serves fixture, agent leak-clean, CI declares `platforms: linux/amd64,linux/arm64` | — |
| R3 | CLI + MCP parity | **pass** | `aws-mcp` starts + `tools/list` → 26 tools; thin boto3 over same endpoint; live CLI↔MCP parity (s3/sqs/dynamodb) | — |
| R4 | Functional coverage | **pass** | `docs/COVERAGE.md` 26-row matrix (endpoint+CLI+MCP+grade), 12 assessment-grade | — |
| R5 | Assessment-grade endpoints | **pass** | 12 assessment-grade; 3 write→read round-trips; typed errors verified live | — |
| R6 | Unit tests all surfaces | **pass** | 63/65 live+docker; MCP parity + isolation (6/6) + 18 per-capability happy/error all green | P2: harden 2 self-standup smoke tests |

### Canon + seeding parity grid (R2 detail) — a–i canon, j–k GHCR image DB seeding
| a | b | c | d | e | f | g | h | i | j | k |
|---|---|---|---|---|---|---|---|---|---|---|
| ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

- **a ✅** base `aws-clone-service` image + published GHCR namespace; `build:`+`image:` so no creds needed.
- **b ✅** `:prod-v1` + `:empty` pair now exist (`Dockerfile.prod-v1`, `Dockerfile.empty`) built from a shared base.
- **c ✅** agent on neutral `python:3.x-slim`; data-free (grep/import/find leak checks clean, verified by `test_isolation`).
- **d ✅** per-task data delivered by **mount** into the gateway only (`./data/aws-clone/state.json:/data/...:ro`), never `COPY`d into a per-task agent image.
- **e ✅** bulk = native `state.json`; mutations replayed via shared seed op-list (boto3).
- **f ✅** reusable sidecar **and** a bundled Harbor-shape task (`oddish/tasks/payment-reconcile/environment/docker-compose.yaml` + `harbor-main-build.override.yaml`); verifier writes `reward.txt`.
- **g ✅** seeding is a gateway-only entrypoint; admin API token-gated; agent can't call it.
- **h ✅** identity-registry applicability documented (N/A for AWS resources) in `docs/PROD-OVERLAY.md`.
- **i ✅** `docs/COVERAGE.md` + PROD-OVERLAY present alongside TOOLS/STATE_SCHEMA/CREATING-TASKS/etc.
- **j ✅** `:prod-v1` bakes `state.json` into `/opt/aws-clone-corpus/state.json` and boots mount-free serving the corpus (`awslocal s3 ls` → `acme-payment-exports`, no `-v`). Switching `empty ↔ prod-v1` is the tag alone (both verified booting).
- **k ✅** leak half clean (`test_isolation` 6/6); multi-arch half satisfied by CI declaring `platforms: linux/amd64,linux/arm64` on base/prod-v1/empty build-push steps (hardened R2.k: declaration accepted locally).

> **Auditor harness notes:** Built the trio locally with clone-specific tags (`awsre/aws-clone-service:{base,prod-v1,empty}`)
> under `COMPOSE_PROJECT_NAME=awsre`. Standup, the task pair, MCP, parity, isolation, and the per-capability
> surface suite were all run against locally-built images (no registry pull needed — `build:`+`image:`). The
> published GHCR multi-arch manifest itself was not pulled (heavy under shared docker); R2.k is scored on the
> CI `platforms:` declaration per the hardened note.

### Coverage matrix audit (R4/R5 detail)
`docs/COVERAGE.md` now exists (26 rows). Audited by **calling each capability live** (CLI via `awslocal`,
MCP via `aws_clone.mcp.tools`/the stdio server) against the booted gateway. MCP column present for every row.

| Capability | Endpoint (LocalStack) | CLI | MCP tool | Envelope OK | Assessment-grade | Tested |
|---|---|---|---|---|---|---|
| S3 list/get/put object | `ListBuckets`/`GetObject`/`PutObject` | `awslocal s3 ls / cp` | `aws_s3_*` | ✅ | ✅ (round-trip; NoSuchKey) | happy+error |
| SQS list/get-url/receive/send | `ListQueues`/`GetQueueUrl`/`ReceiveMessage`/`SendMessage` | `awslocal sqs …` | `aws_sqs_*` | ✅ (real QueueUrls) | ✅ (multi-step round-trip) | happy+error |
| DynamoDB list/get/put/scan | `ListTables`/`GetItem`/`PutItem`/`Scan` | `awslocal dynamodb …` | `aws_dynamodb_*` | ✅ (typed attrs) | ✅ (write→read; the task) | happy+error |
| CloudWatch Logs describe/filter | `DescribeLogGroups`/`FilterLogEvents` | `awslocal logs …` | `aws_logs_*` | ✅ | ✅ (filter grammar) | happy+error |
| SSM get-parameter | `GetParameter` | `awslocal ssm …` | `aws_ssm_get_parameter` | ✅ | — | happy+error |
| Secrets Manager describe | `DescribeSecret` | `awslocal secretsmanager …` | `aws_secrets_describe` | ✅ | — | happy+error |
| EventBridge rules/targets | `ListRules`/`ListTargetsByRule` | `awslocal events …` | `aws_events_*` | ✅ | ✅ (rule→targets) | happy |
| IAM simulate policy | `SimulatePrincipal/CustomPolicy` (shim) | `awslocal iam simulate-*` | `aws_iam_simulate_*` | ✅ (real EvalDecision) | ✅ (query+devops) | happy+error |
| IAM credential report | `Generate/GetCredentialReport` (shim) | `awslocal iam …` | `aws_iam_get_credential_report` | ✅ (real CSV bytes) | ✅ (devops) | happy |
| Kinesis streams/summary | `ListStreams`/`DescribeStreamSummary` | `awslocal kinesis …` | `aws_kinesis_*` | ✅ | ✅ (shard/iterator) | happy |
| STS caller identity | `GetCallerIdentity` | `awslocal sts …` | `aws_sts_get_caller_identity` | ✅ | — | happy |
| Admin/operator snapshot | `/api/_clone/*` (token) | `aws-clonectl state/mutations` | `aws_admin_*` (operator-only) | ✅ | n/a (operator) | happy+error |

Counts: `capabilities_total=26`, `with_cli=26`, `with_mcp=26`, `parity_ok=26`, `assessment_grade=12`,
`tested=26`.

## Action items (ordered, for the creator loop)

1. **[R6 · advisory · P2]** Harden the two compose self-standup smoke tests so they wait for gateway
   health before the first `exec` — they call `docker compose up -d` then immediately `awslocal s3 ls`,
   so they intermittently read empty output before the seed entrypoint finishes (observed: fast-failing
   `assert 'acme-payment-exports' in ''`). Functional behavior they assert is correct once healthy
   (independently verified by waiting on the healthcheck).
   - *where:* `tests/test_localstack_smoke.py`, `tests/test_task_pack_compose.py` (use `docker compose up -d --wait` or poll the healthcheck before the first query).
   - *acceptance:* both green from a cold boot with `AWS_CLONE_RUN_DOCKER_SMOKE=1` without retry.

## Reproduction
```bash
# Cold py3.13 venv
python3.13 -m venv /tmp/awsre-venv && /tmp/awsre-venv/bin/pip install -e ".[dev]"

# R3 headline — MCP server starts + lists tools (26)
/tmp/awsre-venv/bin/python -c "import asyncio; from aws_clone.mcp.server import build_server; \
  print(len(asyncio.run(build_server().list_tools())))"        # → 26
# Real stdio handshake in the agent image
docker build -f Dockerfile.tools -t aws-clone-tools:isolation .
printf '%s\n%s\n%s\n' \
 '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"a","version":"1"}}}' \
 '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
 '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
 | docker run -i --rm aws-clone-tools:isolation timeout 10 aws-mcp 2>&1   # → 26 tools w/ schemas

# Build trio (clone-specific tags)
docker build -f Dockerfile.service -t awsre/aws-clone-service:base .
docker build -f Dockerfile.prod-v1 --build-arg BASE=awsre/aws-clone-service:base -t awsre/aws-clone-service:prod-v1 .
docker build -f Dockerfile.empty   --build-arg BASE=awsre/aws-clone-service:base -t awsre/aws-clone-service:empty .

# R2.j — prod-v1 boots mount-free and serves the baked corpus
docker run -d --name awsre-prod awsre/aws-clone-service:prod-v1   # healthy ~64s
docker exec awsre-prod awslocal s3 ls                             # → acme-payment-exports (NO mount)

# R3 live CLI↔MCP parity (against the running gateway)
AWS_CLONE_RUN_LIVE=1 AWS_CLONE_LIVE_CONTAINER=awsre-prod /tmp/awsre-venv/bin/python -m pytest tests/test_mcp_parity.py -k live -q   # 3 passed
# Per-capability surface (full corpus)
AWS_CLONE_RUN_LIVE=1 AWS_CLONE_LIVE_CONTAINER=awsre-prod /tmp/awsre-venv/bin/python -m pytest tests/test_aws_surface.py -q          # 18 passed

# R6 isolation (builds Dockerfile.tools)
AWS_CLONE_RUN_DOCKER_SMOKE=1 /tmp/awsre-venv/bin/python -m pytest tests/test_isolation.py -v   # 6 passed

# R1 — task nop/oracle
cd oddish/tasks/payment-reconcile/environment
COMPOSE_PROJECT_NAME=awsre docker compose -f docker-compose.yaml -f harbor-main-build.override.yaml up -d --build
# nop: run verifier before any action → reward.txt = 0
# oracle: run solution/solve.sh then verifier → reward.txt = 1
```
