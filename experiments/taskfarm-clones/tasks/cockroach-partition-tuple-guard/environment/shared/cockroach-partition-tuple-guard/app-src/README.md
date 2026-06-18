# CRDB-63642 Local Mirror

This miniature repo mirrors the part of CockroachDB descriptor validation involved in CRDB-63642. The local evidence is synthetic but follows the public Sentry issue: a declarative schema change panics while validating partition tuples for an `ALTER PRIMARY KEY`.

Start with `docs/crdb-63642-evidence.md`, inspect Postgres rows, and run `tools/build_partition_tuple_guard_plan.py` after patching the guard behavior.
