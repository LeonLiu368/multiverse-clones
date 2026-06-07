#!/usr/bin/env bash
# Oracle: fix budget/monitor.py with agreed SLO thresholds + post to #error-budget-reports.
# critical: error_rate>=0.05 or budget>90; warning: error_rate>=0.01 or budget>75;
# should_page: critical always, or warning AND latency_p99_ms>1000.
set -euo pipefail

cat > /workspace/budget/monitor.py << 'PY'
"""Error-budget monitor (per agreed SLO thresholds from #sre-oncall review)."""


def check_budget(
    error_rate: float,
    budget_consumed_pct: float,
    latency_p99_ms: float,
) -> dict:
    if error_rate >= 0.05 or budget_consumed_pct > 90:
        status = "critical"
    elif error_rate >= 0.01 or budget_consumed_pct > 75:
        status = "warning"
    else:
        status = "ok"

    should_page = (status == "critical") or (status == "warning" and latency_p99_ms > 1000)
    return {"status": status, "should_page": should_page}
PY

# Post the notification via the agent's `slack` CLI (consistent tool use).
slack post error-budget-reports "Error budget monitor updated with agreed SLO thresholds. error_rate threshold: 0.05 (critical), 0.01 (warning). budget threshold: 90% (critical), 75% (warning). Paging: always on critical; on warning only if latency p99 > 1000ms."

echo "oracle: fixed budget/monitor.py and posted to #error-budget-reports"
