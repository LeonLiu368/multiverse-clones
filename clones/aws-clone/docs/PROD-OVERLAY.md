# PROD-OVERLAY — canon advisories for aws-clone (R2.h/i)

This note explicitly addresses the converged-canon advisory gates so they are not
silently "undocumented."

## Identity registry (R2.h) — N/A by design

The canon advisory wires people through `abundant-identity` so actors resolve to
shared identities across clones. **aws-clone has no people surface**: its entities
are AWS resources (buckets, queues, tables, log groups, IAM roles/users, streams),
not chat/ticket actors. IAM *users* in the corpus exist only to back the
`GetCredentialReport` and principal-policy simulation surfaces; they are AWS
principals, not cross-clone identities. There is therefore nothing to resolve
through `abundant-identity`, and the registry is intentionally **not** wired. If a
future task needs AWS principals to map to shared identities, seed the IAM
user/role `name` from the identity registry's handles at corpus-authoring time.

## Operator / agent boundary (R2.g) — the PROD overlay

World-building and operator reads are a **gateway-only** surface the agent can
never reach:

- **Seeding** (`python -m aws_clone.seed.load_state`) runs only in the gateway
  entrypoint. The agent image strips `aws_clone/seed` and `aws_clone/admin`
  entirely (see `Dockerfile.tools` / the task `environment/Dockerfile`), so
  `import aws_clone.seed` raises and the corpus is neither greppable nor
  regenerable on the agent (leak rule R2.k, asserted by `tests/test_isolation.py`).
- **Operator reads** (`aws-clonectl state|mutations`, and the MCP `aws_admin_*`
  tools) call the token-gated admin API. The admin API is disabled by default
  (`AWS_CLONE_ENABLE_ADMIN_API=0` → 404) and requires `AWS_CLONE_ADMIN_TOKEN`
  (→ 403 on agent creds). Task packs pass the token to the **gateway only**; the
  agent never receives it, so `aws_admin_*` are operator-only in practice.

## Catalog / skill (R2.i)

The agent-facing tool surface is the real `aws`/`awslocal` CLI plus the `aws-mcp`
MCP server, both thin clients of the same LocalStack HTTP API at
`AWS_ENDPOINT_URL`. The full capability catalog (capability → endpoint → CLI → MCP
tool → fidelity → assessment-grade) lives in `docs/COVERAGE.md`. Tool-launch
details are in `docs/TOOLS.md`.
