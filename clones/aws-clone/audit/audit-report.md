# Clone Audit Report — `aws-clone`

- **Audited:** `2026-06-30` · **Auditor:** `clone-audit v1` · **Commit:** `36e78af`
- **Fidelity tier (declared / observed):** `T3` (OSS-backed / LocalStack) / `T3`
- **Verdict:** ❌ FAILS STANDARD — *(meets = all gating reqs pass)*
- **Gating score:** `2/6` gating requirement-groups pass (R5 ✅, plus R2 a–g runtime gates ✅; R1, R2.b/j/k, R3, R4 fail; R6 partial).

## TL;DR
`aws-clone` is a genuinely high-fidelity **T3 LocalStack-backed** AWS sidecar: agents drive the **real
`aws`/`awslocal` CLI** across 12 services (S3, SQS, SNS, DynamoDB, EventBridge, CloudWatch Logs, SSM,
Secrets Manager, IAM, STS, Lambda-metadata, Kinesis), with a thin **IAM hybrid shim** that fills the
moto/LocalStack gaps (`simulate-principal/custom-policy`, `generate/get-credential-report`) and an
admin `aws-clonectl` verifier CLI. The gateway cold-boots healthy and serves seeded data with real AWS
envelopes (verified live). It does **not** meet Clone Standard v1, primarily because it ships **no MCP
server** (R3, the named "both CLI + MCP" goal), has **no `:prod-v1`/`:empty` baked-DB image trio**
(R2.b/j — data is mount-only), is **published amd64-only** to GHCR (R2.k multi-arch — proven by an
arm64 pull failure), bundles **no task with `test.sh`/`solution`** so nop/oracle is unmeasurable (R1.3),
and has **no `docs/COVERAGE.md`** matrix (R4.1). The single most important action item: **add an
`aws-mcp` server over the same `aws`/`awslocal` surface, wired into the agent image, in CLI parity.**

## What it handles well
- **Real AWS behavior, real envelopes.** Live probes returned authentic shapes: SQS `QueueUrls`
  (`http://sqs.us-east-1.localhost.localstack.cloud:4566/000000000000/payment-webhook-retry`),
  DynamoDB attribute-typed items (`{"event_id":{"S":"evt_001"},"state":{"S":"scheduled"}}`), and the
  real error code `ResourceNotFoundException` (not a 500) for a missing table.
- **Assessment-grade by construction (R5 ✅).** Verified live: write→read round-trip (`put-item` →
  `get-item` returns `done`), realistic typed errors, query grammar via `--query`/`--filter-pattern`,
  and the IAM shim's devops shape (`simulate-custom-policy` → `allowed`, computed from live policy state).
- **Clean agent/operator boundary (R2.g ✅).** Seeding is a service-only entrypoint; admin endpoints are
  token-gated (`check_admin_authorization`: 404 when disabled, 403 on agent creds). The agent tools
  image carries **no** seed corpus: `import aws_clone` raises `ModuleNotFoundError`, grep for the corpus
  answer finds nothing, and `find /opt -path '*/seed/*'` is empty.
- **Data-driven, not generative.** The corpus is a declarative `state.json` replayed through boto3 — no
  deterministic answer-generator to leak.
- **Tests green.** `34/34` pytest pass on a clean 3.13 venv (seed rendering, IAM policy engine,
  credential report, admin auth, state schema, and a CLI/admin parity check against an in-process server).

## Scorecard

| Req | Area | Result | Evidence | Action item (if not full pass) |
|---|---|---|---|---|
| R1 | Setup & run (Harbor) | **fail** | gateway boots healthy in ~54s (emulated) + serves corpus; **but no `tests/test.sh` / `solution/solve.sh` exist** → nop/oracle unmeasurable (R1.3) | Bundle ≥1 task with `test.sh`→`reward.txt` + oracle |
| R2 | Architecture canon a–g + seeding j–k | **fail** | a–g pass (live); **b/j: no `:prod-v1`/`:empty`, no baked DB**; **k: amd64-only** (`docker pull` on arm64 → `no matching manifest for linux/arm64/v8`) | Add image trio + baked-DB; publish multi-arch |
| R3 | CLI + MCP parity | **fail** | exhaustive `grep -ri mcp` over repo → **no matches**; only `aws`/`awslocal`/`aws-clonectl` | Add `aws-mcp` server in CLI parity |
| R4 | Functional coverage | **partial** | real surface covered + envelope-faithful (live), **but `docs/COVERAGE.md` absent** (R4.1) | Write machine-checkable `docs/COVERAGE.md` |
| R5 | Assessment-grade endpoints | **pass** | live: write→read round-trip, typed errors, `--query`/filter grammar, IAM `simulate-custom-policy` | — |
| R6 | Unit tests all surfaces | **partial** | `34/34` pass; **no MCP tests, no in-agent isolation test, no per-capability AWS endpoint tests** | Add isolation + MCP + per-capability tests |

### Canon + seeding parity grid (R2 detail) — a–i canon, j–k GHCR image DB seeding
| a | b | c | d | e | f | g | h | i | j | k |
|---|---|---|---|---|---|---|---|---|---|---|
| ✅ | ❌ | ✅ | ✅ | ✅ | ⚠️ | ✅ | ⚠️ | ⚠️ | ❌ | ❌ |

- **a ✅** base `aws-clone-service` published at `ghcr.io/abundant-ai/aws-clone-service:main` (public, pullable).
- **b ❌** no `:prod-v1` + `:empty` pair — `imagetools inspect …:prod-v1` → `not found`. Only `:main` / `:sha-…` tags.
- **c ✅** agent on neutral base (`python:slim`); data-free (grep/import/find leak checks all clean).
- **d ✅** per-task data delivered by **mount** into the gateway (`./data/aws-clone/state.json:/data/...:ro`), copied to a runtime state file at boot — never `COPY`d into a per-task image.
- **e ✅** bulk = native `state.json`; mutations replayed via shared seed op-list (boto3 calls).
- **f ⚠️** the **reusable sidecar** compose is a clean 2-container agent+gateway with healthcheck + `depends_on`; **but there is no bundled Harbor task** with `test.sh`→`reward.txt` (the verifier half of f is absent).
- **g ✅** world-building (seed) is a gateway-only entrypoint; admin API token-gated; agent can't call it.
- **h ⚠️** no `abundant-identity` wiring (advisory; AWS resources aren't people — likely N/A by design, but undocumented).
- **i ⚠️** good docs (TOOLS/STATE_SCHEMA/CREATING-TASKS/LOCALSTACK-COMPATIBILITY/IMAGE-RELEASE) but **no `docs/COVERAGE.md`** and no PROD-OVERLAY doc.
- **j ❌** `:prod-v1` does not exist; the corpus is **not baked into any image** (`COPY <corpus> → $…_DB` absent from any Dockerfile). The only data path is empty-base + mount. Switching `empty ↔ prod-v1` by tag alone is impossible.
- **k ❌** GHCR image is **single-arch `linux/amd64`** (the index lists only amd64 + an attestation manifest; arm64 pull fails). `Dockerfile.tools` agent is leak-clean (✅ on the leak half), but the **multi-arch half fails** — this is a real fail (the package *is* pullable and demonstrably amd64-only), not `n/a`. CI `build-push-action` declares no `platforms:`; `docs/IMAGE-RELEASE.md` documents `--platform linux/amd64` only.

> **Auditor harness notes:** No `environment/docker-compose.yaml` (Harbor task shape) exists — the clone
> ships as a **reusable sidecar** (`examples/docker-compose.yaml` + `examples/task-pack-compose/`), not a
> bundled task, so the `harbor-main-build.override.yaml` merge was N/A. Standup was done by pulling the
> public GHCR image with `--platform linux/amd64` (forced, because no arm64 manifest exists) and running
> it standalone with the example `state.json` mounted; healthy in ~54s under QEMU emulation. nop/oracle
> could **not** be measured because no `tests/test.sh` or `solution/` is bundled.

### Coverage matrix audit (R4/R5 detail)
No `docs/COVERAGE.md` exists; the matrix below was reconstructed by **calling each capability live**
against the booted gateway. CLI = real `aws`/`awslocal`. MCP column is **absent for every row** (no MCP).

| Capability | Endpoint (LocalStack) | CLI | MCP | Envelope OK | Assessment-grade | Tested |
|---|---|---|---|---|---|---|
| S3 list/get object | `GET /` , `GetObject` | `awslocal s3 ls / cp` | ❌ none | ✅ (real bucket listing) | ⚠️ (read) | smoke |
| SQS list/receive | `ListQueues`/`ReceiveMessage` | `awslocal sqs …` | ❌ none | ✅ (real QueueUrls) | ✅ (multi-step) | smoke |
| DynamoDB get/put/scan | `GetItem`/`PutItem`/`Scan` | `awslocal dynamodb …` | ❌ none | ✅ (typed attrs) | ✅ (write→read round-trip) | smoke |
| CloudWatch Logs filter | `FilterLogEvents` | `awslocal logs filter-log-events` | ❌ none | ✅ | ✅ (filter grammar) | smoke |
| SSM get-parameter | `GetParameter` | `awslocal ssm …` | ❌ none | ✅ | ⚠️ | smoke |
| Secrets Manager describe | `DescribeSecret` | `awslocal secretsmanager …` | ❌ none | ✅ | ⚠️ | smoke |
| EventBridge rules/targets | `ListRules`/`ListTargetsByRule` | `awslocal events …` | ❌ none | ✅ | ⚠️ | smoke |
| IAM simulate policy | `SimulatePrincipal/CustomPolicy` (shim) | `awslocal iam simulate-*` | ❌ none | ✅ (real EvalDecision) | ✅ (query+devops) | ✅ unit (`test_iam_policy`) |
| IAM credential report | `Generate/GetCredentialReport` (shim) | `awslocal iam …` | ❌ none | ✅ (real CSV bytes) | ✅ (devops) | ✅ unit (`test_iam_credreport`) |
| Kinesis streams/records | `CreateStream`/`PutRecords` | `awslocal kinesis …` | ❌ none | ✅ | ✅ (shards/iterator) | ✅ unit (`test_seed_kinesis`) |
| STS caller identity | `GetCallerIdentity` | `awslocal sts …` | ❌ none | ✅ | ⚠️ | smoke |
| Admin/operator snapshot | `/api/_clone/*` (token) | `aws-clonectl state/…` | ❌ none (operator-only) | ✅ | n/a (operator) | ✅ unit (`test_admin_api`) |

Counts: `capabilities_total≈12`, `with_cli=12`, `with_mcp=0`, `parity_ok=0` (no MCP to compare),
`assessment_grade≥6`, `tested` (per-capability) ≈ 4 unit + smoke for the rest.

## Action items (ordered, for the creator loop)

1. **[R3 · gating · P0]** Add an **`aws-mcp` server** exposing the agent-used AWS surface (s3/sqs/dynamodb/logs/ssm/secrets/events/iam/sts/kinesis) as MCP tools, thin over the same LocalStack HTTP API as the CLI, and wire it into the agent image alongside `aws`/`awslocal`.
   - *where:* new `aws_clone/mcp/` (server) + `bin/aws-mcp` + `Dockerfile.tools`/`task-pack-compose/Dockerfile.agent` (install it).
   - *acceptance:* MCP server lists ≥10 tools; a parity test shows `aws s3 ls` and the `s3_list` MCP tool return the same buckets; isolation still holds (no seed in agent).
2. **[R2.b/j · gating · P0]** Build the **image trio**: `aws-clone-service` (base) → `:prod-v1` (corpus **state baked in**, boots and serves the corpus with **no mount**) + `:empty` (mount target). Switching a task must be the **image tag alone**.
   - *where:* `Dockerfile.prod-v1` (`COPY examples/data/.../state.json` into the image + boot-time load) + CI `build-service-image.yml` tags.
   - *acceptance:* `docker run :prod-v1` (no `-v`) → `awslocal s3 ls` returns `acme-payment-exports`; `:empty` + mount also serves mounted data.
3. **[R2.k · gating · P0]** Publish the gateway **multi-arch** (`linux/amd64,linux/arm64`).
   - *where:* `.github/workflows/build-service-image.yml` `build-push-action` → add `platforms: linux/amd64,linux/arm64`; update `docs/IMAGE-RELEASE.md`.
   - *acceptance:* `docker buildx imagetools inspect …:main` lists both `linux/amd64` and `linux/arm64`; `docker pull` succeeds on an arm64 host with no `--platform`.
4. **[R1.3 · gating · P0]** Bundle at least one **runnable task** with `tests/test.sh` (writes `/logs/verifier/reward.txt`) and `solution/solve.sh`, so **nop=0 / oracle=1** is measurable. (The reusable sidecar is solid; the standard needs a bundled task to score R1.)
   - *where:* `environment/docker-compose.yaml` (agent+gateway), `tests/test.sh`, `solution/solve.sh`, a per-task `data/aws-clone/state.json`.
   - *acceptance:* `test.sh` on empty solution → `0.0`; after `solve.sh` → `1.0`.
5. **[R4.1 · gating · P1]** Add a machine-checkable **`docs/COVERAGE.md`** matrix (capability → endpoint → CLI → MCP → fidelity → assessment-grade), labelling ≥5 assessment-grade rows.
   - *where:* `docs/COVERAGE.md`.
   - *acceptance:* every covered capability has a row mapping to endpoint + CLI + (new) MCP tool; ≥5 marked assessment-grade.
6. **[R6.1/R6.2/R6.3 · gating · P1]** Extend tests: **per-capability** AWS endpoint+CLI happy/error tests (not just compose smoke), **MCP** tests + **CLI↔MCP parity** tests, and an **in-agent isolation** test asserting `import aws_clone.seed` raises and no `seed/` source survives.
   - *where:* `tests/test_aws_surface.py`, `tests/test_mcp_parity.py`, `tests/test_isolation.py`.
   - *acceptance:* green from cold boot; parity tests pass for s3/sqs/dynamodb; isolation test asserts ModuleNotFoundError in the agent image.
7. **[R2.h/i · advisory · P2]** Document identity-registry applicability (likely N/A for AWS resources) and add a PROD-OVERLAY note so the canon advisories are explicitly addressed.

## Reproduction
```bash
# Tests (cold, py3.13 venv) — 34/34 pass
uv venv --python 3.13 .venv-audit && .venv-audit/bin/python -m pip install -e ".[dev]"
.venv-audit/bin/python -m pytest tests -q

# No MCP anywhere
grep -ril mcp .                                  # → no matches
# No prod-v1/empty trie, no COVERAGE.md
docker buildx imagetools inspect ghcr.io/abundant-ai/aws-clone-service:prod-v1   # → not found
ls docs/COVERAGE.md                              # → absent

# Multi-arch fail (R2.k): published image is amd64-only
docker buildx imagetools inspect ghcr.io/abundant-ai/aws-clone-service:main      # → only linux/amd64 (+ attestation)
docker pull ghcr.io/abundant-ai/aws-clone-service:main                           # → no matching manifest for linux/arm64/v8

# Agent leak checks (clean) on Dockerfile.tools image
docker build -f Dockerfile.tools -t aws-clone-tools:audit .
docker run --rm aws-clone-tools:audit sh -c "grep -rs 'payment-webhook-retry' /opt /usr/local; echo $?"   # → no match
docker run --rm -e PYTHONPATH=/opt/awscli aws-clone-tools:audit python -c "import aws_clone"               # → ModuleNotFoundError
docker run --rm aws-clone-tools:audit sh -c "find /opt -path '*/seed/*' -o -path '*/api/*'"                # → empty

# Standup (no Harbor task; reusable sidecar) + live capability probes
docker pull --platform linux/amd64 ghcr.io/abundant-ai/aws-clone-service:main
docker run -d --name awsclone_audit --platform linux/amd64 \
  -e AWS_CLONE_ENABLE_ADMIN_API=1 -e AWS_CLONE_ADMIN_TOKEN=test-admin-token-acme-eval \
  -e AWS_ENDPOINT_URL=http://localhost:4566 -e AWS_ACCESS_KEY_ID=test -e AWS_SECRET_ACCESS_KEY=test -e AWS_DEFAULT_REGION=us-east-1 \
  -v "$PWD/examples/data/aws-clone/state.json:/data/aws-clone/state.json:ro" \
  ghcr.io/abundant-ai/aws-clone-service:main                                       # healthy ~54s (emulated)
docker exec awsclone_audit awslocal s3 ls                                          # → acme-payment-exports
docker exec awsclone_audit awslocal sqs list-queues                               # → real QueueUrls
docker exec awsclone_audit sh -lc 'awslocal dynamodb put-item ... ; awslocal dynamodb get-item ...'   # round-trip → done
docker exec awsclone_audit awslocal dynamodb get-item --table-name no_such_table ...  # → ResourceNotFoundException
docker exec awsclone_audit awslocal iam simulate-custom-policy ...                 # → allowed (IAM shim)
docker rm -f awsclone_audit
```
