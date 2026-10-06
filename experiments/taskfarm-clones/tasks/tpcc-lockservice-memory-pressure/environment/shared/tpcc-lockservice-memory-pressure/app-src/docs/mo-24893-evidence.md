# MO-24893 Evidence

Source: matrixorigin/matrixone#24893.

The failing CI job was `80162781342` in namespace `mo-branch-commit-7a8e7cd84-20260608`. The `Start TPCC 1000 Warehouses 1000 terminals Test` step ran from `2026-06-08T18:42:51Z` to `2026-06-08T18:48:42Z`.

Smaller TPCC cases passed first:

- `tpcc_10w_10t`
- `tpcc_10w_100t`
- `tpcc_100w_100t`
- `tpcc_100w_1000t`

At `2026-06-08T18:44:18Z`, terminals started reporting `ErrorCode : 20505` with writes from `10.143.26.142:62466` to backend `10.143.26.143:6003` timing out. Loki showed repeated `cn-service.lockservice failed to lock on remote` for the same backend. Grafana showed the target CN at `54.47Gi / 55Gi`.

Kubernetes did not show a pod restart or OOMKilled event in the TPCC failure window. A later IVF Vector Index failure in the same run did show `OOMKilled` around `2026-06-08T23:49:00Z`; it is useful noise but not the TPCC root cause.
