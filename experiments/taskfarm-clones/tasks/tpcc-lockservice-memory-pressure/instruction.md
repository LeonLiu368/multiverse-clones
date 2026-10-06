Leah needs MO-24893 moved out of incident limbo before the next MatrixOne nightly regression window.

The public issue says the `Start TPCC 1000 Warehouses 1000 terminals Test` step in job `80162781342` failed between `2026-06-08T18:42:51Z` and `2026-06-08T18:48:42Z`. BenchmarkSQL terminals were getting lockservice backend RPC timeouts to `10.143.26.143:6003`. The smaller TPCC cases had already passed, and the target CN `nightly-regression-dis-tp-cn-phqxp` was at about `54.47Gi / 55Gi`. There is also a later IVF vector index `OOMKilled` event in the same run around `2026-06-08T23:49:00Z`; keep it as context, not the TPCC root cause.

Use the local repo, Postgres evidence, Grafana dashboard, static k8s evidence, and TicketVector ticket to make the narrow repair. Do not disable TPCC, do not raise every CN profile, and do not mark Kubernetes OOMKilled as the TPCC failure reason.

Deliverables:

1. Update `/app/src/nightly/tpcc_profiles.yaml` so only `tpcc_1000w_1000t` gets the high-pressure repair profile.
2. Write `/app/artifacts/mo-24893-tpcc-repair.json`.
3. Update the local incident database through the provided tooling.
4. Move TicketVector issue `MO-24893` to `In Review` and add an agent comment with the artifact path, affected profile, target CN, evidence window, and why the later IVF OOM was not used as the root cause.

The repair artifact must be JSON with these top-level keys:

`incident_id`, `affected_profiles`, `untouched_profiles`, `target_cn`, `root_cause`, `changes`, `evidence_window_utc`, `broad_workaround_avoided`.

`affected_profiles` is a list of objects containing `id`, `warehouses`, and `terminals`. `untouched_profiles` is a list of profile ids. `target_cn` is an object with `pod`, `ip`, `backend`, `memory_observed_gib`, and `memory_limit_gib`. `changes` is an object that includes `cn_memory_limit_gib` and `lockservice_rpc_timeout_ms`.

TicketVector issue data exposes a `state` object, and comments expose `author.handle` and `body`; use those fields when confirming your handoff.
