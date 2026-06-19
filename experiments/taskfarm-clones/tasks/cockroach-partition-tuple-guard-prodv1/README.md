# Cockroach Partition Tuple Guard

This task is grounded in TaskFarm candidate `cand_ca95696c565668e5`, derived from the public CockroachDB Sentry issue for CRDB-63642.

Local services:

- `main`: agent workspace with repo files and clone CLIs
- `postgres`: descriptor validation and incident state
- `github`: seeded `acme/cockroach-partition-tuple-guard` repository
- `sentry`: Sentry clone with the CRDB-63642 panic and nearby noise
- `ticketvector`: CRDB-63642 handoff and related tickets

The verifier is deterministic and checks final behavior/state rather than source substrings.
