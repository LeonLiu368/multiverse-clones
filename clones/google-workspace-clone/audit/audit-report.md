# Audit (RE-AUDIT) — google-workspace-clone

- **Clone:** `google-workspace-clone` (Google Workspace: Drive v3 + Docs v1 + Calendar v3 + Gmail v1)
- **Commit:** `b2b2abd`  ·  **Audited:** 2026-06-30  ·  **Standard:** clone-standard-v1
- **Fidelity tier:** declared **T2**, observed **T2** (handwritten FastAPI + SQLite with a real Drive `q` / Gmail-operator / Calendar time-window query grammar, plus a Calendar write)
- **Verdict: MEETS STANDARD — 6 / 6 gating requirements pass.** Round-1 was 4/6 (FAIL R4/R5/R6); the fixer's claim of 6/6 is **CONFIRMED** by independent run.

## TL;DR

This is the second pass after a fix round. All three previously-failing gates now pass, verified by
running — not reading: `docs/COVERAGE.md` is a real 12-row matrix with 6 assessment-grade rows (R4); an
agent-facing **Calendar `events.insert`** write is reachable from both `gws-cli calendar create` and the
`gws_create_event` MCP tool, and the bundled `gws-create-event` task does a genuine write→read
round-trip (NOP=0, ORACLE=1, grader reads the event back through the API) (R5); and `pytest` from a cold
3.13 venv runs **75 passed / 2 skipped** covering every endpoint, CLI command, MCP tool, plus parity and
isolation (R6). R1/R2 regressions hold: the rebuilt `:prod-v1` serves its baked corpus mount-free and the
freshly-built agent image is leak-sealed (no seed on disk, `import gwsclone.seed` raises, answer not
greppable). **One P1 non-gating caveat:** the currently-published/cached image trio is stale (2026-06-25,
Drive-only) and must be republished from current source so a `docker pull` user gets the write surface.

## What it handles well (verified, not read)

- **Cold boot + mount-free prod-v1 (R1/R2.j).** Rebuilt `gws-local/gworkspace-service:prod-v1` boots Healthy with NO fixture mount and serves **28 baked Drive files**; needle query `name contains 'Q3 Launch Plan'` → 2 docs (needle + DRAFT decoy). No `networks:` block in any task compose.
- **Leak-sealed agent (R2.c/g/k, R6.3).** In a freshly-built `Dockerfile.agent` image with no source mount: 7/7 leak checks PASS — `gwsclone.seed` not importable, no `/srv/gws.db`, no `api/`/`seed/` dir, `import gwsclone.seed` → `ModuleNotFoundError`, no `seed/import/hydrate/snapshot` on PATH, `2026-09-15` not greppable in `/opt /app /usr/local`.
- **CLI + MCP parity, now incl. write (R3).** 12 MCP tools (incl. `gws_create_event`); `test_parity.py` asserts CLI==MCP per capability + identical 404 envelope, green in the cold run. Rebuilt `:empty` openapi exposes the full surface incl. `POST /calendar/v3/calendars/{id}/events`.
- **Write→read round-trip (R5.2).** Live against rebuilt `:empty`: `POST .../events` → server-minted base32hex id → `events.list q=` reads it back. Bundled task: NOP grade=0, oracle reads the Gmail thread (rejecting the Oct-3 draft-bot decoy), writes `Q3 Retro` via `gws-cli calendar create`, hidden grader reads it back through `events.list q='Q3 Retro'` → PASS at the confirmed 2026-10-06T14:00, NOT the draft date.
- **Faithful envelopes (R4.3).** Live: `drive#fileList`, `calendar#events`, `calendar#event`, `{error:{code,message,status}}` with 401 UNAUTHENTICATED / 404 NOT_FOUND / 400 INVALID_ARGUMENT.
- **Comprehensive tests (R6).** `test_api.py` (29 endpoint tests, happy+error incl. insert roundtrip + 401/404/400), `test_cli.py`, `test_mcp.py` (12 tools over real stdio JSON-RPC), `test_parity.py`, `test_isolation.py`, `test_roundtrip.py`, `test_query.py`. **75 passed / 2 skipped** in 111s from a cold venv.

## Scorecard

| Req | Result | Gating | Evidence (one command) |
|---|---|---|---|
| R1 Setup & run | **pass** | yes | `docker run -d :prod-v1` → Healthy; `/drive/v3/files` = 28 files mount-free; nop=0/oracle=1 on write task |
| R2 Agent+gateway / seeding | **pass** | yes | rebuilt agent image: 7/7 leak checks PASS; multi-arch declared in CI; per-task mount into gateway only |
| R3 CLI + MCP parity | **pass** | yes | 12 MCP tools; `test_parity.py` green; rebuilt `:empty` openapi = full Drive/Docs/Calendar(+POST)/Gmail |
| R4 Coverage matrix | **pass** | yes | `docs/COVERAGE.md` = 12-cap matrix, 6 assessment-grade rows, write→read row, envelope section |
| R5 Assessment-grade | **pass** | yes | `gws-cli calendar create` + `gws_create_event` present in agent image; bundled task nop=0/oracle=1 |
| R6 Unit tests | **pass** | yes | cold-venv `pytest tests -q` = **75 passed, 2 skipped**; isolation runs green inside the agent image |

### R2 canon sub-grid

| a | b | c | d | e | f | g | h | i | j | k |
|---|---|---|---|---|---|---|---|---|---|---|
| pass | pass | pass | pass | pass | pass | pass | n/a | pass | **pass** | **pass** |

(h identity registry not wired — advisory/n-a; i CI publish workflow now present.)

## Coverage-matrix audit (clone now ships docs/COVERAGE.md)

| # | Capability | Endpoint | CLI | MCP | envelope | assess | tested |
|---|---|---|---|---|---|---|---|
| 1 | Drive list (q) | GET /drive/v3/files | `drive ls -q` | gws_list_files | ✅ | ✅ | api/cli/mcp/parity |
| 2 | Drive get | GET /drive/v3/files/{id} | `drive get` | gws_get_file | ✅ | – | api/cli/mcp/parity |
| 3 | Drive export/media | …/export, ?alt=media | `drive export` | gws_get_file_text | ✅ | – | api/cli/mcp |
| 4 | Docs get | GET /v1/documents/{id} | `docs get` | gws_get_document | ✅ | ✅ | api/cli/mcp/parity |
| 5 | Docs text (derived) | (client) | `docs text` | gws_get_document_text | ✅ | – | cli/mcp/parity/query |
| 6 | Docs search (derived) | (client) | `docs search` | gws_search_document | ✅ | – | cli/mcp |
| 7 | Calendar list (q+window) | GET …/events | `calendar events` | gws_list_events | ✅ | ✅ | api/cli/mcp/parity |
| 8 | Calendar get | GET …/events/{id} | `calendar get` | gws_get_event | ✅ | – | api/cli/mcp |
| 9 | **Calendar create (WRITE→READ)** | POST …/events | `calendar create` | gws_create_event | ✅ | ✅ | api/cli/mcp/parity/roundtrip |
| 10 | Gmail search (operators) | GET …/messages | `gmail search` | gws_search_messages | ✅ | ✅ | api/cli/mcp/parity/query |
| 11 | Gmail get | GET …/messages/{id} | `gmail get` | gws_get_message | ✅ | – | api/cli/mcp |
| 12 | Gmail thread | GET …/threads/{id} | `gmail thread` | gws_get_thread | ✅ | ✅ | api/cli/mcp |

12/12 with CLI, 12/12 with MCP, 12/12 parity, **6 assessment-grade** (≥5 required), **all 12 tested at the surface**. Row 9 is the write→read round-trip.

## Confirm/deny per previously-failing gate

- **R4 — CONFIRM (was fail).** `docs/COVERAGE.md` now exists and is a genuine matrix (capability→endpoint→CLI→MCP→envelope→assess→tested), 6 assessment-grade rows ≥ the 5 required, operator-only routes segregated. *Cmd:* `cat docs/COVERAGE.md`.
- **R5 — CONFIRM (was fail).** Agent-facing write present on both surfaces and exercised end-to-end. *Cmd:* boot `:empty`+task fixture; `bash oddish/tasks/gws-create-event/solution/solve.sh` (oracle writes via gws-cli) then `pytest tests/trusted/test_grade_event.py` (grader reads back via API) → NOP fail / ORACLE pass.
- **R6 — CONFIRM (was fail).** Full surface suite. *Cmd:* `python3.13 -m venv v && v/bin/pip install -e '.[dev,mcp]' && v/bin/python -m pytest tests -q` → 75 passed, 2 skipped; in-image isolation: `docker run --rm <agent-img> python -c '<leak asserts>'` → all PASS.

## Regressions (R1/R2)

- **R1/R2 hold.** `:prod-v1` boots mount-free and serves the baked corpus (28 files); freshly-built agent image is leak-sealed (7/7). No regression introduced by the write feature.

## Remaining blockers / caveats

- **None gating.** `meets_standard = true`.
- **P1 (non-gating, R2):** the *published/cached* image trio (`gworkspace-service:{empty,prod-v1}`, `gworkspace-agent`) is dated 2026-06-25 and predates the write work — the cached `:prod-v1` openapi shows only Drive+Docs and POST events returns FastAPI `{"detail":"Not Found"}`; the cached agent image has no `gws-cli calendar create`. Source + Dockerfiles are correct (rebuild produces full write-capable, leak-sealed images, verified), so this is a publish-staleness item, not a design defect. Republish via the CI workflow on next push-to-main.
- **P2 (non-gating, R5):** `seed gen-corpus` for `:prod-v1` emits calendar:0/gmail:0 (Drive+Docs only). Fine today (the write task uses `:empty`+per-task fixture), but a future prod-v1-difficulty write task would need baked events.

## Reproduction

```bash
cd clones/google-workspace-clone
export COMPOSE_PROJECT_NAME=gwsre

# R6 — cold-venv full surface suite (needs py>=3.11)
python3.13 -m venv /tmp/gws-cv13 && /tmp/gws-cv13/bin/pip install -e ".[dev,mcp]"
/tmp/gws-cv13/bin/python -m pytest tests -q              # 75 passed, 2 skipped

# R1/R2.j — rebuilt prod-v1 boots mount-free
docker build -f docker/Dockerfile -t gwsre/service:empty .
python -m gwsclone.cli.main seed gen-corpus --out docker/gws_corpus.db
docker build -f docker/Dockerfile.prod-v1 --build-arg BASE=gwsre/service:empty -t gwsre/service:prod-v1 docker
docker run -d --name gwsre-prodv1 -p 18097:8080 gwsre/service:prod-v1
curl -s -H "Authorization: Bearer gws-clone-token" localhost:18097/drive/v3/files   # 28 files

# R2/R6.3 — leak-sealed agent image
docker build -f docker/Dockerfile.agent -t gwsre/agent .
docker run --rm gwsre/agent python -c 'import importlib.util,os,gwsclone; \
  assert importlib.util.find_spec("gwsclone.seed") is None; assert not os.path.exists("/srv/gws.db")'

# R5.2 — write→read round-trip (nop=0 / oracle=1)
docker run -d --name gw -p 18094:8080 \
  -v "$PWD/oddish/tasks/gws-create-event/environment/data/gws/fixture.json:/srv/fixture.json:ro" gwsre/service:empty
export GWS_API_URL=http://localhost:18094 GWS_TOKEN=gws-clone-token PATH="/tmp/gws-cv13/bin:$PATH"
cp oddish/tasks/gws-create-event/tests/trusted/test_grade_event.py /tmp/test_g.py
python -m pytest /tmp/test_g.py -q          # NOP: 1 failed (reward 0)
bash oddish/tasks/gws-create-event/solution/solve.sh   # oracle writes Q3 Retro via gws-cli
python -m pytest /tmp/test_g.py -q          # ORACLE: 1 passed (reward 1)
```
