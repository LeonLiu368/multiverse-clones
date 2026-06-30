# Phase 3 — Unit-test every endpoint, CLI command, and MCP tool (R6)

Goal: a green test run that proves **every surface works**, the CLI and MCP **agree** (parity), and
the agent **can't read the answer key** (isolation). If the clone's tests don't cover this, generate
the missing ones from `assets/test_clone_template.py`.

## Coverage bar (R6.1)
For **every** row in the Phase-2 coverage matrix, you need:
- **Endpoint test** — call the HTTP API directly; assert status + envelope shape (ids, fields).
- **CLI test** — invoke the CLI command; assert exit code + parsed output.
- **MCP test** — call the MCP tool; assert the structured result.
- **≥1 error path each** — bad id / missing arg / unauthorized → assert the *real* error envelope and
  a sane exit code, not a stack trace or 500.

Don't settle for "the suite is green" — green over 20% of the surface is an R6 **partial**. Diff the
test inventory against the coverage matrix and list every untested capability as an action item.

## Parity tests (R6.2)
The most valuable tests in a CLI+MCP clone. For each capability:
```python
cli_out  = run_cli("issue", "view", "ENG-2016", "--json")
mcp_out  = call_mcp_tool("get_issue", {"id": "ENG-2016"})
assert normalize(cli_out) == normalize(mcp_out)   # same data, both thin clients of one API
```
A failure here means the surfaces have drifted — they aren't both reading one HTTP source of truth
(violates R3.2). This is exactly the regression the standard exists to catch.

## Isolation test (R6.3) — grep is not enough
```python
# in the agent image / main container
assert not os.path.exists(STATE_PATH)             # no seed on disk  (R2.g/c)
assert health_over_http() == 200                  # state reachable only via the service
# the leak that passed grep in the notion dogfood: a recomputable answer via an importable generator
with pytest.raises(ModuleNotFoundError):
    __import__(f"{PKG}.seed")                      # gateway generator NOT importable from the agent
assert not glob.glob(f"{OPT}/**/seed/*", recursive=True)   # no seed/ or api/ source survives
```
Also assert world-building entrypoints (import/seed/hydrate/snapshot) are **not** on the agent's PATH.
**Why:** a deterministic seed generator left in the agent lets the agent regenerate the world and read
the answer off-disk, even when a literal grep for the answer finds nothing (the answer is *computed*).
Strip the gateway's `api/`+`seed/` from the agent image (or build it from a neutral base).

## Running from cold (R6.4)
Tests must pass from a fresh `docker compose up` — not against a warm dev box with hand-loaded state.
Wire the suite into `test.sh` or CI. Record `<passed>/<total>` and the exact invocation.

## Envelope-shape assertions (R6.5, advisory)
Pin id prefixes, error codes, and pagination cursors so a future fidelity regression fails a test
rather than silently shipping. Cheap, high-value, but advisory.

## Generating missing tests
`assets/test_clone_template.py` is a parametrized pytest scaffold with:
- a `clone` fixture (base URL, auth, CLI runner, stdio MCP client),
- `ENDPOINTS` / `CLI_CASES` / `MCP_CASES` / `PARITY_CASES` tables you fill from the coverage matrix,
- happy + error parametrizations, plus the isolation test.

Fill the tables, run `pytest -q`, and fold the result into the report. Tests you generate to *measure*
the clone should be left in the clone's `tests/` (or `tests/audit/`) so the next audit and the verifier
reuse them — the audit grows the clone's own coverage.

## Carry into the report
- `tests.passed` / `tests.total`, plus `nop_reward` / `oracle_reward` from Phase 1.
- Every red test → an action item tagged with the requirement it blocks (usually R6, sometimes R4/R3).
