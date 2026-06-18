# CRDB-63642 Evidence

Sentry issue `sentry_7461557230` reports:

```text
errors.go:82: executing declarative schema change StatementPhase stage 1 of 1
with 24 MutationType ops (rollback=false) for ALTER TABLE: runtime error:
slice bounds out of range [2:0]
```

The stack runs through `pkg/sql/rowenc.DecodePartitionTuple`, `valueside.Decode`, `DecodeUntaggedDatum`, and `DecodeUntaggedBytesValue` before descriptor validation writes the updated descriptor.

For this task, the production capture was normalized into `descriptor_validation_cases`. Two CRDB-63642 rows have empty tuple bytes even though the tuple arity is nonzero. A nearby CRDB-63590 row has an intentional zero-arity empty list and must not be changed.
