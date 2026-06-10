from payments.retry_policy import MAX_ATTEMPTS, retry_delay_ms, retry_plan, should_retry
from payments.replay import load_events, replay_events

assert MAX_ATTEMPTS >= 1
assert retry_delay_ms(1) > 0
assert retry_plan(503)["retry"] is True
assert isinstance(retry_plan(503).get("capped"), bool)
assert should_retry(400) is False
visible = replay_events(load_events())
assert visible["replayed_events"] >= 1
assert "scheduled_retries" in visible

print("payment visible checks passed")
