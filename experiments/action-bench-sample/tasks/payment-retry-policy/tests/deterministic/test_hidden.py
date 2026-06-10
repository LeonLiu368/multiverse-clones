from payments.retry_policy import MAX_ATTEMPTS, BASE_DELAY_MS, MAX_DELAY_MS, JITTER_RATIO, retry_delay_ms, retry_plan, should_retry_event
from payments.replay import replay_events

assert MAX_ATTEMPTS == 5
assert BASE_DELAY_MS == 250
assert MAX_DELAY_MS == 4000
assert JITTER_RATIO == 0.20
assert [retry_delay_ms(i) for i in range(1, 6)] == [250, 500, 1000, 2000, 4000]
for status in (429, 500, 502, 503, 504):
    assert retry_plan(status)["retry"] is True
assert retry_plan(425, {"status_code": 425, "idempotent": True})["retry"] is True
assert retry_plan(409, {"status_code": 409, "error_type": "lock_conflict", "idempotent": True})["retry"] is True
assert retry_plan(503)["capped"] is True
assert retry_plan(400)["capped"] is False
assert should_retry_event({"status_code": 425, "idempotent": True}) is True
assert should_retry_event({"status_code": 425, "idempotent": False}) is False
assert should_retry_event({"status_code": 409, "error_type": "lock_conflict", "idempotent": True}) is True
assert should_retry_event({"status_code": 409, "error_type": "validation_conflict", "idempotent": True}) is False

holdout = [
    {"id": "h_429_retry_after", "status_code": 429, "idempotent": True, "retry_after_ms": 5000},
    {"id": "h_425_safe", "status_code": 425, "idempotent": True},
    {"id": "h_425_unsafe", "status_code": 425, "idempotent": False},
    {"id": "h_409_lock", "status_code": 409, "error_type": "lock_conflict", "idempotent": True},
    {"id": "h_409_generic", "status_code": 409, "error_type": "validation_conflict", "idempotent": True},
    {"id": "h_terminal", "status_code": 503, "idempotent": True, "persistent_failure": True},
]
summary = replay_events(holdout)
assert summary["replayed_events"] == 6
assert summary["scheduled_retries"] == 4, summary
assert summary["skipped_non_retryable"] == 2, summary
assert summary["unsafe_retries"] == 0, summary
assert summary["terminal_failures"] == 1, summary
assert summary["capped_retries"] == 4, summary
retry_after_decision = next(d for d in summary["decisions"] if d["event_id"] == "h_429_retry_after")
assert retry_after_decision["delays_ms"][0] == 4000, retry_after_decision

# the webhook dispatcher schedules retries too -- it must agree with the policy
# module on delays, conditional 409/425 retryability, and attempt count
from payments.webhooks import webhook_retry_schedule
for consistency_event in (
    {"status_code": 503, "idempotent": True},
    {"status_code": 429, "idempotent": True},
    {"status_code": 409, "error_type": "lock_conflict", "idempotent": True},
    {"status_code": 425, "idempotent": True},
):
    expected_delays = retry_plan(consistency_event["status_code"], dict(consistency_event))["delays_ms"]
    assert webhook_retry_schedule(dict(consistency_event)) == expected_delays, consistency_event
assert webhook_retry_schedule({"status_code": 425, "idempotent": False}) == []
assert webhook_retry_schedule({"status_code": 409, "error_type": "validation_conflict", "idempotent": True}) == []
assert webhook_retry_schedule({"status_code": 400}) == []

print("payment hidden checks passed")
