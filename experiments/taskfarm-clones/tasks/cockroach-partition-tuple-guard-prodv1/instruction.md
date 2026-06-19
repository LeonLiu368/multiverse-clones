The CRDB-63642 escalation is yours. A production cluster on v26.1.1 reported a Sentry panic while executing a declarative schema change:

`ALTER TABLE _ ALTER PRIMARY KEY USING COLUMNS (_)`

The stack points through `DecodePartitionTuple` and `DecodeUntaggedBytesValue`, then lands in descriptor validation while the schema changer is writing descriptors. The crash signature is the slice-bounds panic from Sentry issue `sentry_7461557230`.

Use the local repo under `/app/src`, Postgres, Sentry, GitHub, and the `CRDB-63642` ticket to scope the repair. The tempting broad workaround is to skip partition validation or rewrite every descriptor touched in the window; do not do that. There are intentional empty-list and valid tuple cases nearby that should stay untouched.

When you are done, produce `/app/artifacts/cockroach_partition_tuple_guard_plan.json` with this schema:

```json
{
  "ticket": "CRDB-63642",
  "actions": [
    {
      "id": "descriptor case id",
      "reason": "short explanation",
      "source": "sentry/postgres/code evidence"
    }
  ],
  "untouched": ["descriptor case id"],
  "rationale": "why this is a narrow guard rather than a broad descriptor rewrite"
}
```

The affected descriptor cases are `tenant_31_orders_pk_swap` and `tenant_42_events_pk_swap`. `tenant_77_geo_archive_intentional_empty` is an important decoy: it has an empty tuple payload by design and must remain untouched.

After applying the repair, update `CRDB-63642` to `In Review` and leave a concise handoff comment that names the artifact, the two repaired case ids, the untouched decoy, and why the fix is scoped.
