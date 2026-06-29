# Clone Audit Report — `<clone-name>`

- **Audited:** `<YYYY-MM-DD>` · **Auditor:** `clone-audit vX` · **Commit:** `<sha>`
- **Fidelity tier (declared / observed):** `<T1>` / `<T1>`
- **Verdict:** ✅ MEETS STANDARD · ⚠️ PARTIAL · ❌ FAILS  — *(meets = all gating reqs pass)*
- **Gating score:** `<n>/<total>` gating requirements pass.

## TL;DR
2–4 sentences: what this clone is, whether it's usable for agent assessment today, and the single
most important action item.

## What it handles well
- Bullet the genuinely strong points (cite evidence: endpoint, test, file:line).

## Scorecard

| Req | Area | Result | Evidence | Action item (if not full pass) |
|---|---|---|---|---|
| R1 | Setup & run (Harbor) | pass/partial/fail | `nop=0.0 oracle=1.0`, boot log | … |
| R2 | Architecture canon a–g | pass/partial/fail | parity grid below | … |
| R3 | CLI + MCP parity | pass/partial/fail | parity test output | … |
| R4 | Functional coverage | pass/partial/fail | `docs/COVERAGE.md` ✓/✗ | … |
| R5 | Assessment-grade endpoints | pass/partial/fail | N labelled, round-trip demo | … |
| R6 | Unit tests all surfaces | pass/partial/fail | `<n>` passed / `<m>` total | … |

### Canon parity grid (R2 detail)
| a | b | c | d | e | f | g | h | i |
|---|---|---|---|---|---|---|---|---|
| ✅ | ✅ | ✅ | ⚠️ | ❌ | ✅ | ✅ | ⚠️ | ✅ |

### Coverage matrix audit (R4/R5 detail)
| Capability | Endpoint | CLI | MCP | Envelope OK | Assessment-grade | Tested |
|---|---|---|---|---|---|---|
| e.g. search issues | `POST /graphql` | `jira issue query` | `search_issues` | ✅ | ✅ (query grammar) | ✅ |

## Action items (ordered, for the creator loop)
1. **[R<x> · gating]** Concrete, file-scoped fix. *(what to change, where, acceptance check)*
2. **[R<x> · advisory]** …

## Reproduction
Exact commands the auditor ran (standup, probes, test invocation) so the result is reproducible.
