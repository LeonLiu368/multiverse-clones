"""Rolling-window utilities for the error-budget monitor (correct — no changes needed)."""
from typing import Sequence


def rolling_error_rate(successes: Sequence[int], failures: Sequence[int]) -> float:
    """Compute error rate over a rolling window from per-bucket success/failure counts."""
    total_s = sum(successes)
    total_f = sum(failures)
    total = total_s + total_f
    if total == 0:
        return 0.0
    return total_f / total


def clamp(value: float, lo: float, hi: float) -> float:
    """Clamp value to [lo, hi]."""
    return max(lo, min(hi, value))
