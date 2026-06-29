# Fidelity tiers, OSS-vs-handwrite, and the one-matrix CLI+MCP pattern

The three decisions that most shape a clone's quality and cost. Make them explicitly and record them
in the clone spec.

## Fidelity tiers

| Tier | What it is | Store | Reach assessment-grade? | Use when |
|---|---|---|---|---|
| **T0** | fixture echo — canned responses, no state | none | ❌ no | never ship as a clone (demo only) |
| **T1** | stateful handwritten — own HTTP API, real envelopes | SQLite / JSON / DuckDB | partial (round-trips, errors) | default; most clones |
| **T2** | T1 **+ a real query grammar** | same | ✅ yes | when agents must *construct queries* (the discriminating skill) |
| **T3** | OSS engine behind a translation layer | the engine's store | ✅ yes (highest) | a faithful OSS engine exists and fidelity > weight |

**The standard is tier-agnostic for *passing*** — a clean T1 clone can meet R1–R6. But R5 requires ≥5
**assessment-grade** capabilities, and several of the five signals (query grammar especially) push you
toward T2. Pick the lowest tier at which you can hit R5 for your service, then stop — extra fidelity
the tasks don't use is wasted container weight.

Examples in the fleet: Figma/GWS/Sentry/Slack-gateway = T1–T2 handwritten; Gauge (PromQL/LogQL),
Logfire (SQL) = T2 by virtue of query grammar; gh (Forgejo), AWS (LocalStack) = T3 OSS-backed.

## OSS-vs-handwrite decision rubric

Score the candidate service. Lean **OSS (T3)** if most of these hold; **handwrite (T1/T2)** otherwise.

| Question | Favors OSS | Favors handwrite |
|---|---|---|
| Is the agent-used surface **large & well-specified**? | yes (don't reimplement GitHub) | no — a handful of endpoints |
| Does a **faithful, self-hostable OSS engine** exist? | yes (Forgejo, LocalStack, Mattermost) | no (Slack, Figma, Sentry SaaS-only) |
| How much does **container weight / cold-boot speed** matter? | tolerant | strict (single-container, fast reset) |
| Do you need **byte-deterministic** ids/state for grading? | engine may wobble | full control |
| Is **single-container isolation** required? | adds a sidecar engine | one process, easy |
| Maintenance: can you live with **upstream drift**? | yes | you own it anyway |

Decision recorded as: `T3 (Forgejo) — large GitHub surface, faithful OSS exists, weight acceptable` or
`T1 handwritten — small Figma read surface, no OSS engine, determinism required`.

**Crucial caveat:** OSS replaces only the **engine**. You *always* handwrite (and own) the three things
the standard grades: the **translation layer** (real-API shape over the engine), the **CLI**, and the
**MCP server**. Adopting LocalStack doesn't get you an MCP for free — see `aws-clone`, which is T3 but
**fails R3** because it never built one.

When OSS *almost* fits: write a thin **shim** for the few operations it lacks rather than abandoning it
(aws-clone's IAM `simulate-principal-policy` botocore shim is the model). Shim < reimplement < fork.

## The one-matrix CLI+MCP pattern (how to satisfy R3 by construction)

Parity drift is the #1 way clones fail R3. Prevent it structurally: **generate both surfaces from one
capability table over one shared HTTP client.** Don't hand-maintain two lists.

```
capability table (== docs/COVERAGE.md rows)
        │
        ▼
   shared HTTP client  (the ONLY thing that talks to the API)
        ├──────────────► CLI command   (thin: parse args → client call → format)
        └──────────────► MCP tool       (thin: schema → client call → structured result)
```

Rules that keep them in parity:
1. **No logic in the CLI or MCP.** Both call the shared client; the client calls the HTTP API; the API
   is the only source of truth. (R3.2)
2. **One capability ⇒ one CLI command **and** one MCP tool**, named consistently
   (`issue view` ↔ `get_issue`). Operator-only capabilities are excluded from *both*, not exposed in one.
3. **A parity test per capability** (CLI output == MCP output) lives in `tests/` and runs in CI. The
   auditor's R6.2 test should pass on day one because you wrote the same test. (mirror
   `clone-audit/assets/test_clone_template.py`)
4. **Fix at the API/client layer.** When the auditor flags a bug, fix it once below the fork so both
   surfaces inherit the fix — never patch the CLI and MCP separately.

Retrofitting MCP onto a CLI-only clone (aws, jira): extract the CLI's HTTP calls into the shared client
if they aren't already, then add an MCP server that imports it. Net new code is the tool schemas, not
the logic.
