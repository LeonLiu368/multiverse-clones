"""On-call paging decision.

This caused a pager-fatigue incident: the alert paged on a single transient spike. The team
diagnosed the root cause and agreed a NEW paging policy in the incident discussion, but it was
never written into this repo. Recover the agreed policy from the workspace incident channel
and implement `should_page` accordingly.
"""


def should_page(error_rate: float, consecutive_breaches: int) -> bool:
    """Return True iff on-call should be paged, given the current window's `error_rate`
    (0.0-1.0) and how many `consecutive_breaches` have occurred so far.

    Implement per the paging policy the team agreed in the workspace incident postmortem.
    """
    raise NotImplementedError(
        "should_page is unimplemented — recover the agreed paging policy from the workspace "
        "incident discussion (the pager-fatigue postmortem) and implement it here."
    )
