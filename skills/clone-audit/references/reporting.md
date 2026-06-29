# Phase 4 — Report & verdict (R7)

Goal: two artifacts that close the loop — a human-readable `audit-report.md` and a machine-readable
`audit-verdict.json`. Write both into the clone repo (e.g. `clones/<name>/audit/` or the clone root).

## 1. `audit-report.md` (from `_shared/audit-report-template.md`)
Fill every section. The parts that matter most for the loop:
- **What it handles well** — be specific and fair; the creator needs to know what *not* to break.
- **Scorecard** — R1–R6 with `pass|partial|fail` and one evidence cell each.
- **Canon parity grid** — a–i as ✅/⚠️/❌.
- **Coverage-matrix audit** — the table built in Phase 2.
- **Action items** — ordered, **gating first**, each file-scoped with an acceptance check.
- **Reproduction** — the commands you ran, so the result is re-runnable.

## 2. `audit-verdict.json` (conforms to `_shared/audit-verdict.schema.json`)
The structured twin of the report. Populate:
- `requirements.R1..R6` with `{result, gating, evidence, sub}` (use `sub` for R2's a–i).
- `coverage` counts and `tests` counts (incl. `nop_reward`/`oracle_reward`).
- `action_items[]` — each with `requirement`, `gating`, `priority`, `summary`, `where`, `acceptance`.
- `meets_standard` and `fidelity_tier {declared, observed}`.

## 3. The meets-standard decision (don't fudge)
```
meets_standard = (every gating requirement result == "pass")
```
Gating = R1, R2.a–g, R3, R4, R5, R6. A single gating `fail` ⇒ `meets_standard = false`. There is no
partial credit on the verdict bit — a clone that boots beautifully but has a CLI/MCP parity gap, <5
assessment-grade endpoints, or untested surfaces **does not meet the standard**. Say so plainly and
put those gaps at the top of the action list.

## 4. Action-item discipline (this is the feedback signal)
Each item must be **falsifiable by the next audit**:
- `summary`: what's wrong, in one line.
- `where`: the file/component to change (`clones/aws-clone/aws_clone/mcp/` — to be created).
- `acceptance`: the exact check that flips it to pass (`MCP server lists ≥10 tools; parity test green
  for s3/sqs/dynamodb`).
- `priority`: P0 = gating blocker, P1 = gating-adjacent or high-value advisory, P2 = polish.

Order: all P0/gating, then P1, then P2. The creator works the list top-down.

## 5. Hand back to the loop
Print a one-paragraph summary to the user: verdict, gating score (`n/total`), the top 3 action items,
and whether this is ready to hand to `clone-creation` for another pass. If `meets_standard` is already
true with no P0s, say the clone is **eval-ready** and the loop has converged.

## Multi-clone runs
Auditing the whole fleet? Emit one verdict JSON per clone and a roll-up table (clone × R1–R6 + meets)
so the fleet's readiness is visible at a glance and the worst gaps are obvious to prioritize.
