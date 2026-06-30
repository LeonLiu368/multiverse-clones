# Audit — google-workspace-clone

- **Clone:** `google-workspace-clone` (Google Workspace: Drive v3 + Docs v1 + Calendar v3 + Gmail v1)
- **Commit:** `36e78af`  ·  **Audited:** 2026-06-30  ·  **Standard:** clone-standard-v1
- **Fidelity tier:** declared **T2**, observed **T2** (handwritten FastAPI + SQLite with a real Drive `q` / Gmail-operator / Calendar time-window query grammar)
- **Verdict: DOES NOT MEET STANDARD** — 4 / 6 gating requirements pass. Three gating gaps: no coverage matrix (R4), no write→read round-trip / read-only surface (R5), and near-absent surface tests (R6).

## TL;DR

This is a genuinely strong, faithful read clone with excellent runtime hygiene. The agent+gateway
runtime is exemplary: `:prod-v1` bakes the corpus DB and serves it **mount-free**, the GHCR images are
**public, pullable, and multi-arch**, the thin agent is **leak-sealed** (no seed on disk, `seed`
module not importable, answer not greppable), CLI and MCP are in **verified live parity** over one HTTP
API, and **nop=0 / oracle=1** was measured end-to-end with the answer recovered through `gws-cli`
against an adversarial needle-among-decoys corpus. What it lacks is the **scaffolding the standard
gates on**: there is no `docs/COVERAGE.md`, the agent surface is **entirely read-only** (so no
write→read round-trip can be exercised, R5.2), and the test suite is 6 store-level query tests with **no
endpoint / CLI / MCP / parity / isolation coverage** (R6).

## What it handles well (verified, not read)

- **Cold boot, Harbor-style (R1).** `docker compose up --build -d` on `gws-launch-date-prod-v1`: gateway → Healthy, agent started, agent reaches `http://gworkspace:8080/health` by service name. No `networks:` block in any task compose.
- **GHCR image-DB seeding (R2.j).** prod-v1 served **28 baked drive files with no fixture mount**; `docker pull ...:prod-v1` => "Image is up to date" (public, creds-free).
- **Multi-arch (R2.k).** `imagetools inspect` shows `linux/amd64` + `linux/arm64` on `:prod-v1`, `:latest`, and `:empty`.
- **Leak-sealed agent (R2.c/g/k).** In the built agent image: no `/srv/gws.db`; no `api/`/`seed/` source; `import gwsclone.seed` → `ModuleNotFoundError`; answer `2026-09-15` not greppable in `/opt /app /usr/local`.
- **CLI + MCP parity (R3).** 11 MCP tools, 11 CLI commands, both thin HTTP clients of one API; live checks: CLI `docs text` == MCP `gws_get_document_text`, CLI/MCP calendar `q=LaTeX` both ==1, identical 404 error envelope across CLI and MCP.
- **Faithful envelopes (R4.3).** Live: `drive#fileList`, `calendar#events`, `{error:{code,message,status}}` with 401 UNAUTHENTICATED / 404 NOT_FOUND / 400 INVALID_ARGUMENT.
- **Real query grammar (T2 / R5.1).** Drive `q` (name/fullText/mimeType contains/=/!=, `'id' in parents`, trashed, and/or/not/parens — `fullText` searches Doc bodies); Gmail `from:/to:/subject:/label:` + space-AND/OR/parens; Calendar `q` + `[timeMin,timeMax)`. Invalid Drive terms → 400, like Google.
- **Real, high-volume fixtures.** `gws-event-room` mounts **115 drive / 103 docs / 1735 calendar / 2000 gmail** items from a genuine Gmail Takeout export (real sender addresses observed live). `gws-launch-multihop` chains Calendar→Gmail.
- **nop=0 / oracle=1 (R1.3).** Stock `plan.py` (`"TODO"`) → 2 pytest failures → reward 0. Oracle recovers `2026-09-15` via `gws-cli docs text` (disambiguating the "DRAFT — superseded" decoy) → 2 passed → reward 1.
- **Determinism (R1.6).** `seed gen-corpus` twice → byte-identical drive-id set.

## Scorecard

| Req | Result | Gating | Evidence (one command) |
|---|---|---|---|
| R1 Setup & run | **pass** | yes | `compose up --build -d` → Healthy; pull prod-v1 creds-free; nop=0/oracle=1 measured in-container |
| R2 Agent+gateway / seeding | **pass** | yes | prod-v1 28 files mount-free; multi-arch inspect; `import gwsclone.seed`→ModuleNotFoundError |
| R3 CLI + MCP parity | **pass** | yes | 11 MCP tools listed; CLI `docs text` == MCP `gws_get_document_text` live |
| R4 Coverage matrix | **fail** | yes | `docs/` does not exist → no `COVERAGE.md` (R4.1 absent) |
| R5 Assessment-grade | **fail** | yes | all agent endpoints GET (grep routes) → no write→read round-trip (R5.2) |
| R6 Unit tests | **fail** | yes | `pytest -q` = 6/6 but only `test_query.py` store tests; no endpoint/CLI/MCP/parity/isolation |

### R2 canon sub-grid

| a | b | c | d | e | f | g | h | i | j | k |
|---|---|---|---|---|---|---|---|---|---|---|
| pass | pass | pass | pass | pass | pass | pass | n/a | fail | **pass** | **pass** |

(h identity registry not wired — advisory; i skill+catalog+PROD-OVERLAY doc absent — advisory.)

## Coverage-matrix audit (reconstructed — clone ships none)

| Capability | Endpoint | CLI | MCP | envelope | assess-grade | tested |
|---|---|---|---|---|---|---|
| Drive list (q-grammar) | GET /drive/v3/files | `drive ls -q` | gws_list_files | ✅ | ✅ | live only |
| Drive get | GET /drive/v3/files/{id} | `drive get` | gws_get_file | ✅ | – | live only |
| Drive export/media | GET …/export, ?alt=media | `drive export` | gws_get_file_text | ✅ | – | no |
| Docs get | GET /v1/documents/{id} | `docs get` | gws_get_document | ✅ | ✅ | no |
| Docs text (derived) | (client) | `docs text` | gws_get_document_text | ✅ | – | yes (store) |
| Docs search (derived) | (client) | `docs search` | gws_search_document | ✅ | – | no |
| Calendar list (q+window) | GET …/events | `calendar events` | gws_list_events | ✅ | ✅ | live only |
| Calendar get | GET …/events/{id} | `calendar get` | gws_get_event | ✅ | – | no |
| Gmail search (operators) | GET …/messages | `gmail search` | gws_search_messages | ✅ | ✅ | yes (store) |
| Gmail get | GET …/messages/{id} | `gmail get` | gws_get_message | ✅ | – | no |
| Gmail thread | GET …/threads/{id} | `gmail thread` | gws_get_thread | ✅ | ✅ | no |

11/11 with CLI, 11/11 with MCP, 11/11 parity, ~5 assessment-grade (all read), 2 tested at the surface
(only via store-level tests). **Zero** write capabilities.

## Ordered action items

1. **[P0 · R6]** Add a test suite covering every endpoint, every CLI command, every MCP tool (happy + ≥1 error each) + a CLI↔MCP **parity** test + an **isolation** test (`no /srv/gws.db`, `import gwsclone.seed` raises). *Where:* `tests/` (model on `clone-audit/assets/test_clone_template.py`). *Accept:* green from cold boot, all 11 caps + error paths + parity + isolation covered.
2. **[P0 · R5]** Add ≥1 agent-facing **write** capability (Drive `files.create`/Docs `batchUpdate`/Calendar `events.insert`/Gmail `drafts.create`) through API+CLI+MCP and a bundled task that writes→reads it. *Where:* `api/app.py`, `store.py`, `cli/main.py`, `mcp/server.py`, `oddish/tasks/<new>`. *Accept:* a task's `solve.sh` writes via a tool and a later read observes it; nop=0/oracle=1.
3. **[P0 · R4]** Create `docs/COVERAGE.md` (machine-checkable: endpoint | CLI | MCP | envelope-OK | assessment-grade | tested) covering all four surfaces; label ≥5 assessment-grade incl. the new round-trip. *Accept:* every capability row maps to real endpoint+CLI+MCP.
4. **[P1 · R4 advisory]** Fix stale `README.md` — it claims only "Drive + Docs slice" but Calendar v3 + Gmail v1 are fully implemented and exercised (1735 events / 2000 messages). *Accept:* README documents all four surfaces + links COVERAGE.md.
5. **[P2 · R2 advisory]** Add a GHCR-publish CI workflow (push-to-main, `packages: write`, multi-arch buildx, tags `:latest/:sha/:empty/:prod-v1`) so the publish contract is automated rather than hand-run via `build-prod-v1.sh --push`.

## Reproduction

```bash
# install (needs py>=3.11; py3.9 system python is rejected by requires-python)
python3.13 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest tests/ -q                       # 6 passed

# live API + CLI/MCP
.venv/bin/gws-cli seed load fixtures/acme.json --out /tmp/acme.db
GWS_DB=/tmp/acme.db .venv/bin/uvicorn gwsclone.api.app:app --port 8099 &
GWS_API_URL=http://127.0.0.1:8099 GWS_TOKEN=t .venv/bin/gws-cli docs text DOC_Q3PLAN_0001

# Harbor standup + nop/oracle + leak checks
cd oddish/tasks/gws-launch-date-prod-v1/environment
MAIN_IMAGE_NAME=gws-audit-main:latest docker compose \
  -f docker-compose.yaml -f <skills>/clone-audit/assets/harbor-main-build.override.yaml up --build -d
docker exec environment-main-1 sh -c "curl -fsS http://gworkspace:8080/drive/v3/files -H 'Authorization: Bearer gws-clone-token' | jq '.files|length'"  # 28, mount-free
docker exec environment-main-1 sh -c "python -c 'import gwsclone.seed'"  # ModuleNotFoundError
docker buildx imagetools inspect ghcr.io/abundant-ai/gworkspace-service:prod-v1  # amd64 + arm64
```

## Gates that were static-only (not dynamically exercised)

- **R5.1 assessment-grade labelling** — assessed by reading routes + live query probes, not against a shipped matrix (none exists).
- **R2.h/i** (identity registry, skill/catalog/PROD-OVERLAY doc) — advisory, judged by file presence (absent).
- The `:empty + mount` path was confirmed by config + GHCR inspect + a local seed-and-serve of the event-room fixture (1735/2000 items) on the host uvicorn, not a second container standup (one docker standup, to share the pool).
- nop/oracle were reproduced by running the verifier's pytest logic **inside the live agent container** (the answer recovered through `gws-cli`), equivalent to `tests/test.sh`'s `code_ok` path.
