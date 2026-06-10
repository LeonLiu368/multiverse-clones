# payment-retry-policy

Incident workflow task for a payment retry outage. The agent must use Linear/Jira and Slack to recover the final policy, update `/app/src`, run the local payment replay, and use `/app/artifacts/payment_retry_replay.json` as evidence in Slack and the issue tracker.

Multi-container GitHub + Slack + Linear incident task. Agent sees `/app/src`, `linear`, `jira`, `slack`, and `gh`. TicketVector, Slack, and GitHub state are sidecar-owned.

The agent must open, wait for CI on, and merge a local GitHub pull request in `acme/payment-retry-policy` and link that PR back through the ticket workflow.

## Verification

Verification is LLM-as-judge by design. `tests/test.sh` collects structured evidence (git/PR
state with per-PR diffs, artifacts, full Slack channel histories, ticket comment bodies, and
the outputs of the deterministic checks preserved under `tests/deterministic/`) and has
`cursor/composer` grade it against `tests/rubric.json`: six weighted criteria with strict
scoring anchors, mandatory gates for code behavior / artifact / PR mechanics (0.9 threshold),
and continuous partial-credit reward with hard zero floors for mandatory failures and
anti-cheat violations. Purely deterministic verification is insufficient here because half the graded surface
(naturally worded Slack handoffs, ticket comments articulating the recovered policy, PR
rationale) has no single correct string; exact-match checks produce false failures on
correct work. The deterministic checks remain
as evidence anchors the judge must reconcile with. The verifier is Python stdlib only (no
third-party dependencies) and fails closed to reward 0 on any judge or runtime error. Verifier-only tooling (the judge CLI) is installed by `test.sh` at verification time from a
version-pinned, sha256-verified tarball; the agent image contains no verifier tooling. Judge
discretion is bounded: code, artifact, and PR mechanics are decided by the deterministic checks
and the mandatory floors -- the reference solution scores 1.0 and an empty run scores 0 under
this verifier.
