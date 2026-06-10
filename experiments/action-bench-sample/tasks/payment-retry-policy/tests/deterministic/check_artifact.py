import json
from pathlib import Path

artifact = Path("/app/artifacts/payment_retry_replay.json")
assert artifact.exists(), f"missing replay artifact: {artifact}"
data = json.loads(artifact.read_text())

assert data["replayed_events"] == 8, data
assert data["scheduled_retries"] == 5, data
assert data["skipped_non_retryable"] == 3, data
assert data["unsafe_retries"] == 0, data
assert data["terminal_failures"] == 1, data
assert data["capped_retries"] == 5, data

by_id = {d["event_id"]: d for d in data["decisions"]}
assert by_id["pay_003"]["retry"] is False, by_id["pay_003"]
assert by_id["pay_005"]["retry"] is False, by_id["pay_005"]
assert by_id["pay_008"]["capped"] is True, by_id["pay_008"]

print("payment artifact checks passed")
