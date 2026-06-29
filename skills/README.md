# skills — the clone creator↔auditor loop

Two matched skills that standardize how clones are built and verified in this monorepo, plus the
shared contract they both target.

```
_shared/
  clone-standard.md          THE contract — requirements R1–R7 both skills agree on
  audit-report-template.md   human-readable audit report shape
  audit-verdict.schema.json  machine-readable audit verdict (closes the loop)
clone-creation/              BUILDER — create a clone to the standard
  SKILL.md
  references/{fidelity-and-oss, clone-spec}.md
clone-audit/                 AUDITOR — verify a clone against the standard
  SKILL.md
  references/{setup-and-run, functional-coverage, unit-tests, reporting}.md
  assets/{audit_harness.sh, test_clone_template.py}
```

## The loop

```
clone-creation  ──emits──►  clone + clone-spec.yaml
                                   │
                              clone-audit
                                   │
                          audit-verdict.json  (per-req pass/partial/fail + action_items)
                                   │
                  meets_standard? ─┴─ no ──► clone-creation works action_items top-down ──► re-audit
                                   │
                                  yes ──► eval-ready (loop converged)
```

- **Contract:** `_shared/clone-standard.md` (R1 setup/run · R2 **agent+gateway** canon + **GHCR image
  DB seeding** · R3 CLI+MCP parity · R4 coverage · R5 assessment-grade endpoints · R6 unit tests · R7
  report). Every clone runs as two containers — a built **agent** + a pulled/seeded **gateway** whose
  `:prod-v1` image bakes the corpus DB. Gating reqs must all pass to "meet" it.
- **Builder:** `clone-creation` builds *to* the standard and emits a `clone-spec.yaml`.
- **Auditor:** `clone-audit` boots the clone, audits CLI+MCP coverage, unit-tests every surface, and
  emits a report + verdict whose `action_items` feed the next build.

Both build on the deeper architecture in the global `service-clone-builder` skill
(`~/.claude/skills/service-clone-builder/`) and its `references/the-converged-canon.md`; they
standardize the decisions around it and wire the result into an automatable loop.

## Using them
- New clone: invoke **clone-creation**, follow its five decisions, self-audit before handoff.
- Existing clone (e.g. anything under `../clones/`): invoke **clone-audit** to get a verdict + action
  items, then **clone-creation** to work them.
- Fleet sweep: run **clone-audit** per clone and roll up the verdicts (see `clone-audit` reporting).
