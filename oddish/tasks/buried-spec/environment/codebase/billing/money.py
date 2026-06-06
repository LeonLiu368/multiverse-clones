"""Small money helpers. These work and are covered by passing tests — leave them green."""


def format_cents(cents: int) -> str:
    """Format integer cents as a dollar string, e.g. 12345 -> '$123.45'."""
    if not isinstance(cents, int):
        raise TypeError("cents must be an int")
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}${cents // 100}.{cents % 100:02d}"


def parse_dollars(s: str) -> int:
    """Parse a dollar string like '$123.45' or '123.45' into integer cents."""
    s = s.strip().lstrip("$").strip()
    if "." in s:
        whole, frac = s.split(".", 1)
        frac = (frac + "00")[:2]
    else:
        whole, frac = s, "00"
    return int(whole) * 100 + int(frac)
