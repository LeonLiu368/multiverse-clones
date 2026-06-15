"""Analytics pipeline integration (correct — no changes needed here)."""
from .publisher import build_event_payload


def emit(event_name: str, user_id: str, properties: dict | None = None) -> dict:
    """Emit an event to the analytics pipeline."""
    payload = build_event_payload(event_name, user_id, properties or {})
    # In production this POSTs to the pipeline endpoint; tests mock the return value.
    return {"queued": True, "payload": payload}
