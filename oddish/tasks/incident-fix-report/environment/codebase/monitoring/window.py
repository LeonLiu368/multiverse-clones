"""Window helpers. These work and are covered by passing tests — leave them green."""


def error_rate(ok_count: int, error_count: int) -> float:
    """Fraction of requests in a window that errored. 0.0 when there is no traffic."""
    total = ok_count + error_count
    if total <= 0:
        return 0.0
    return error_count / total
