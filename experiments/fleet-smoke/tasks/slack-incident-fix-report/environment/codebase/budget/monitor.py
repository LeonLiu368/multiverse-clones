"""Error-budget monitor.

The alerting thresholds were reconfigured after an SLO review. The agreed thresholds
and paging conditions are in the workspace — check #sre-oncall.
"""


def check_budget(
    error_rate: float,
    budget_consumed_pct: float,
    latency_p99_ms: float,
) -> dict:
    """Evaluate current service health against the SLO error-budget policy.

    Returns {"status": "ok"|"warning"|"critical", "should_page": bool}.

    The thresholds were revised in the SLO review — recover the agreed values
    from the workspace (#sre-oncall) before updating this function.
    """
    # These conditions are WRONG — recover the agreed policy from #sre-oncall.
    if error_rate > 0.10 or budget_consumed_pct > 95:
        status = "critical"
    elif error_rate > 0.05 or budget_consumed_pct > 90:
        status = "warning"
    else:
        status = "ok"

    should_page = (status == "critical")  # missing the latency+warning condition

    return {"status": status, "should_page": should_page}
