#!/usr/bin/env bash
# Oracle: rewrite build_event_payload to v2 spec.
# event_name, actor_id, attributes, recorded_at (int ms), schema_version=2 (int)
set -euo pipefail

cat > /workspace/events/publisher.py << 'PY'
"""Analytics event publisher (v2 format per #data-platform announcement)."""
import time as _time


def build_event_payload(
    name: str,
    user_id: str,
    data: dict,
    timestamp: float | None = None,
) -> dict:
    ts = timestamp if timestamp is not None else _time.time()
    return {
        "event_name": name,
        "actor_id": user_id,
        "attributes": data,
        "recorded_at": int(ts * 1000),
        "schema_version": 2,
    }
PY

echo "oracle: updated events/publisher.py to v2 schema"
