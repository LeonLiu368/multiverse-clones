# TPCC Lockservice Memory Pressure

This task is grounded in MatrixOne issue 24893: a nightly TPCC 1000W/1000-terminal run failed with lockservice RPC timeouts while the target CN was nearly at its memory limit. The runnable environment provides a local app repo, Postgres incident tables, TicketVector state, GitHub clone state, and Grafana dashboard evidence.

The expected repair is scoped to the single high-pressure TPCC profile and leaves smaller TPCC cases plus the later IVF OOMKilled noise untouched.
