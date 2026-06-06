#!/usr/bin/env bash
# Oracle: the correct multi-step incident response, performed entirely through mmctl.
set -euo pipefail
TEAM="${MM_TEAM:-test-demo}"

# 1. Investigate (read the incident thread).
mmctl post list "${TEAM}:incidents" -n 50 >/dev/null 2>&1 || true

# 2. Post the root cause to #incidents.
mmctl post create "${TEAM}:incidents" -m "ROOT CAUSE: connection pool exhaustion. The checkout-api v2.3 deploy raised worker concurrency 4x (8 -> 32 per pod); each worker holds its own Postgres connection pool, so total connections blew past max_connections=100 and checkout requests queued waiting for a free connection — driving the p99 latency and 5xx spike."

# 3. Open a dedicated incident channel.
mmctl channel create --team "$TEAM" --name inc-checkout-latency --display-name "INC checkout latency" >/dev/null 2>&1 || true

# 4. Post a status summary to the new channel.
mmctl post create "${TEAM}:inc-checkout-latency" -m "SUMMARY: checkout-api p99 latency and 5xx spike (16:50-17:06 UTC) was caused by connection pool exhaustion after the v2.3 deploy quadrupled worker concurrency. Mitigation: rolled back to v2.2; DB connections and latency recovered. Follow-up: cap per-worker pool size (pgbouncer) or raise max_connections before re-deploying v2.3."

echo "oracle: posted ROOT CAUSE to #incidents, created #inc-checkout-latency, posted SUMMARY"
