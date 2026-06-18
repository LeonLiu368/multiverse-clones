# Descriptor Backref Repair Reproduction

CRDB-63963 tracks a catalog validation panic from a CockroachDB v25.4.0 cluster. The local builder reads descriptor evidence from Postgres, runs `catalog_repair.planner.plan_repairs`, and writes `/app/artifacts/descriptor_backref_repair.json`.

The repair target is deliberately narrow: public relation descriptors whose `depended_on_by` validation failed because the referenced descriptor is missing. Healthy references, dropped descriptors, and other validation keys are operational noise.
