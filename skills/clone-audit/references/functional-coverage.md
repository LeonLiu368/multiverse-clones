# Phase 2 — Functional coverage: CLI + MCP vs the real API (R3, R4, R5)

Goal: an **audited coverage matrix** proving the clone covers the real service's agent-used surface
through **both** a CLI and an MCP server in parity, with enough **assessment-grade** endpoints to
discriminate agents. Fill every cell by **calling the tool**, never by reading source.

## Step 1 — Establish the target surface (R4.1)
Prefer the clone's `docs/COVERAGE.md`. If it's missing or thin, reconstruct the "API surface agents
actually use" from the real product (Stage-0 study in `service-clone-builder`). Capture, per
capability: the real endpoint, the real CLI verb, whether agents read or write it, and the real
response envelope (id prefixes, error codes, pagination). A missing/insufficient `COVERAGE.md` is an
R4 action item even if behavior is fine — the loop needs the matrix to be machine-checkable.

## Step 2 — Enumerate what the clone exposes
- **CLI:** walk the command tree — `<cli> --help`, then `<cli> <group> --help` for each group. Record
  every leaf command and its flags.
- **MCP:** start the server and **list tools** (initialize → `tools/list`). Record every tool + its
  input schema. (See `assets/test_clone_template.py` for a minimal stdio MCP client.)
- Map each CLI command and MCP tool back to the HTTP endpoint it calls.

## Step 3 — Build the audited matrix
One row per capability:

| Capability | Endpoint | CLI cmd | MCP tool | Envelope OK | Assessment-grade | Tested |
|---|---|---|---|---|---|---|

Populate **Envelope OK** by issuing the call and diffing the response shape against the real product.
Leave **Tested** for Phase 3. A capability with an endpoint but no CLI **or** no MCP is a coverage/
parity gap unless explicitly operator-only.

## Step 4 — Parity audit (R3.3 — the core "both CLI + MCP" check)
For each capability, run the CLI path and the matching MCP tool against the same state and confirm
they return the **same underlying data**. Classify each:
- ✅ both present, agree
- ⚠️ both present, disagree (drift — they aren't both thin clients of one API; **R3.2/R3.3**)
- ❌ one missing (CLI-only or MCP-only; **R3.1/R3.3** — the named goal is *both* surfaces)

The "give every clone CLI + MCP" objective is judged here. Two known gaps in the current fleet:
`aws-clone` (no MCP — agents drive real `aws`/`awslocal`) and `abundant-jira-clone` (no MCP — CLI
only, tooling lives in `ticketvector`). Expect those to fail R3 until an MCP is added.

## Step 5 — Envelope fidelity (R4.3)
Per covered endpoint, verify: id prefixes (`C…`/`U…`, `ENG-…`, `1:2` node ids), error **envelopes**
(real `{ "ok": false, "error": "…" }` / GraphQL errors / HTTP status), and **pagination** shape
(cursor vs page token vs offset). Wrong-shaped errors (a 500 where the real API returns a typed error)
are an R4 finding — they leak that it's a clone and weaken devops realism.

## Step 6 — Assessment-grade labelling (R5)
A capability is **assessment-grade** when it has ≥3 of:
1. **Stateful** — a write is observable on a later read.
2. **Multi-step** — realistic use chains ≥2 calls (list → filter → act).
3. **Realistic errors** — bad input returns the product's real error, not a generic 500.
4. **Query grammar** — agent must build a non-trivial query (JQL, Slack search operators, PromQL,
   Drive `q`, Sentry issue search, log SQL).
5. **Side-effecting devops shape** — deploy/dispatch, resolve/assign, redeliver, rotate, query logs
   to find a cause.

Require **≥5 labelled** (≥3 for small clones, R5.1) and **≥1 write→read round-trip** exercised by a
bundled task (R5.2). Prefer a spread across read-investigation and write-action (R5.3, advisory).
Too few assessment-grade capabilities = R5 fail: a clone that only echoes fixtures can't tell a good
agent from a bad one, so it's not eval-useful no matter how cleanly it boots.

## Carry into the report
- The completed matrix (becomes the "Coverage matrix audit" table).
- R3/R4/R5 results with counts: `capabilities_total`, `with_cli`, `with_mcp`, `parity_ok`,
  `assessment_grade`. These populate `coverage` in the verdict JSON.
