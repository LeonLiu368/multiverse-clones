# Cockroach Descriptor Backref Repair

This task is grounded in a CockroachDB Sentry issue where catalog validation panicked on a depended-on-by back reference to a missing descriptor. The local task keeps the incident scoped to a repair planner, Postgres catalog evidence, Sentry stack context, a seeded GitHub repository, and a TicketVector handoff.

Reviewers should expect the solution to repair planner behavior, generate `/app/artifacts/descriptor_backref_repair.json`, update only the affected descriptor rows in Postgres, and move `CRDB-63963` to `In Review` with a scoped comment. The verifier checks runtime behavior and final state rather than source substrings.
