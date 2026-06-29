from __future__ import annotations

from aws_clone.seed.load_state import seed_kinesis


class FakeKinesis:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def create_stream(self, **kwargs):
        self.calls.append(("create_stream", kwargs))

    def describe_stream_summary(self, StreamName):
        return {"StreamDescriptionSummary": {"StreamStatus": "ACTIVE"}}

    def put_records(self, **kwargs):
        self.calls.append(("put_records", kwargs))

    def add_tags_to_stream(self, **kwargs):
        self.calls.append(("add_tags_to_stream", kwargs))

    def increase_stream_retention_period(self, **kwargs):
        self.calls.append(("increase_stream_retention_period", kwargs))

    def decrease_stream_retention_period(self, **kwargs):
        self.calls.append(("decrease_stream_retention_period", kwargs))


def _of(fake: FakeKinesis, name: str) -> list[dict]:
    return [kwargs for call, kwargs in fake.calls if call == name]


def test_creates_provisioned_stream_with_records():
    state = {
        "kinesis": {
            "streams": [
                {
                    "name": "telemetry-ingest",
                    "shard_count": 2,
                    "tags": {"team": "platform"},
                    "records": [
                        {"partition_key": "device-1", "data": "hello"},
                        {"partition_key": "device-2", "data_json": {"event": "drop"}},
                    ],
                }
            ]
        }
    }
    fake = FakeKinesis()
    seed_kinesis(state, {"kinesis": fake})

    create = _of(fake, "create_stream")[0]
    assert create["StreamName"] == "telemetry-ingest"
    assert create["ShardCount"] == 2
    records = _of(fake, "put_records")[0]
    assert records["StreamName"] == "telemetry-ingest"
    assert len(records["Records"]) == 2
    assert records["Records"][0]["Data"] == b"hello"
    assert records["Records"][0]["PartitionKey"] == "device-1"
    assert records["Records"][1]["Data"] == b'{"event":"drop"}'
    assert _of(fake, "add_tags_to_stream")[0]["Tags"] == {"team": "platform"}


def test_on_demand_stream_mode():
    state = {"kinesis": {"streams": [{"name": "events", "stream_mode": "ON_DEMAND", "records": []}]}}
    fake = FakeKinesis()
    seed_kinesis(state, {"kinesis": fake})
    create = _of(fake, "create_stream")[0]
    assert create["StreamModeDetails"] == {"StreamMode": "ON_DEMAND"}
    assert "ShardCount" not in create
    assert _of(fake, "put_records") == []  # no records -> no put


def test_retention_increase_decrease():
    fake = FakeKinesis()
    seed_kinesis({"kinesis": {"streams": [{"name": "s", "retention_hours": 168, "records": []}]}}, {"kinesis": fake})
    assert _of(fake, "increase_stream_retention_period")[0]["RetentionPeriodHours"] == 168
    fake2 = FakeKinesis()
    seed_kinesis({"kinesis": {"streams": [{"name": "s", "retention_hours": 12, "records": []}]}}, {"kinesis": fake2})
    assert _of(fake2, "decrease_stream_retention_period")[0]["RetentionPeriodHours"] == 12


def test_missing_kinesis_key_is_noop():
    fake = FakeKinesis()
    seed_kinesis({}, {"kinesis": fake})
    assert fake.calls == []
