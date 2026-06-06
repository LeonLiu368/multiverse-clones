"""Overdue-fee calculation.

The exact overdue-fee policy (grace period, tier rates, minimum, cap, rounding) was
debated and AGREED by the team in the workspace billing discussion. It is NOT written down
in this repo. Read the workspace history to recover the agreed policy, then implement it.
"""


def overdue_fee(balance_cents: int, days_overdue: int) -> int:
    """Return the overdue fee, in integer cents, for an account `days_overdue` days past
    due with the given outstanding `balance_cents`.

    Implement per the policy the team agreed in the workspace (the billing-policy
    discussion). The result must be a non-negative integer number of cents.
    """
    raise NotImplementedError(
        "overdue_fee is not implemented — recover the agreed policy from the workspace "
        "billing-policy discussion and implement it here."
    )
