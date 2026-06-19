# Loki BoltDB Cache Isolation

This task recreates a Loki write-path CrashLoopBackOff incident inspired by grafana/loki#3248. The runtime includes a seeded repo, Postgres incident data, TicketVector ticket state, Grafana dashboard evidence, and lightweight Kubernetes evidence objects.

The deliverable is unsolved in its initial state. A correct solution scopes the BoltDB shipper path change to `loki-write-2` and `loki-write-5`, generates `/app/artifacts/loki_boltdb_repair.json`, updates Postgres through the audit tool, and hands off `LOKI-3248` in TicketVector.
