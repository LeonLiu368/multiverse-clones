"""Analytics event publisher.

The analytics pipeline migrated to schema v2. The new field names and format
requirements were announced in the workspace — check #data-platform.
"""
import time as _time


def build_event_payload(
    name: str,
    user_id: str,
    data: dict,
    timestamp: float | None = None,
) -> dict:
    """Build the analytics event payload for the pipeline.

    IMPORTANT: The pipeline now requires v2 format. The field names and types changed.
    Recover the v2 spec from the workspace (#data-platform) and update this function.
    """
    ts = timestamp if timestamp is not None else _time.time()
    # v1 format — WRONG, needs updating to v2
    return {
        "name": name,            # v1 field name
        "user_id": user_id,      # v1 field name
        "data": data,            # v1 field name
        "timestamp": ts,         # v1: float seconds
        "schema_version": "1",   # v1: string, not int
    }
