import json
from pathlib import Path

from payments.retry_policy import retry_plan, event_status

APP_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE = APP_ROOT / "data" / "payment_incident" / "visible_fixture.jsonl"
DEFAULT_ARTIFACT = Path("/app/artifacts/payment_retry_replay.json")


def load_events(path: str | Path = DEFAULT_FIXTURE) -> list[dict]:
    events: list[dict] = []
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line:
            events.append(json.loads(line))
    return events


def replay_events(events: list[dict]) -> dict:
    summary = {
        "replayed_events": 0,
        "scheduled_retries": 0,
        "capped_retries": 0,
        "terminal_failures": 0,
        "unsafe_retries": 0,
        "skipped_non_retryable": 0,
        "decisions": [],
    }
    for event in events:
        status = event_status(event)
        plan = retry_plan(status, event)
        retry = bool(plan.get("retry"))
        unsafe = retry and (
            (status == 425 and not event.get("idempotent", bool(event.get("idempotency_key"))))
            or (status == 409 and event.get("error_type") != "lock_conflict")
        )
        if retry:
            summary["scheduled_retries"] += 1
            if plan.get("capped"):
                summary["capped_retries"] += 1
            if event.get("persistent_failure"):
                summary["terminal_failures"] += 1
        else:
            summary["skipped_non_retryable"] += 1
        if unsafe:
            summary["unsafe_retries"] += 1
        summary["replayed_events"] += 1
        summary["decisions"].append(
            {
                "event_id": event.get("id"),
                "status_code": status,
                "retry": retry,
                "capped": bool(plan.get("capped")),
                "unsafe": unsafe,
                "delays_ms": plan.get("delays_ms", []),
            }
        )
    return summary


def write_replay(path: str | Path = DEFAULT_ARTIFACT, fixture: str | Path = DEFAULT_FIXTURE) -> dict:
    summary = replay_events(load_events(fixture))
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary
