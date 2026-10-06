import json
import os
import subprocess
from pathlib import Path


artifact = Path("/app/artifacts/cockroach_partition_tuple_guard_plan.json")
assert artifact.exists(), f"missing {artifact}"
data = json.loads(artifact.read_text())
found = sorted(action["id"] for action in data["actions"])
expected = ["tenant_31_orders_pk_swap", "tenant_42_events_pk_swap"]
assert found == expected, found
assert data["ticket"] == "CRDB-63642", data
assert "tenant_77_geo_archive_intentional_empty" in data["untouched"], data
assert "tenant_77_geo_archive_intentional_empty" not in found, data
rationale = data.get("rationale", "").lower()
assert "narrow" in rationale or "scoped" in rationale, rationale
assert "skip all" in rationale or "broad" in rationale or "rewrite every" in rationale, rationale


def psql(sql):
    return subprocess.check_output(
        ["psql", "-X", "-q", "-t", "-A", "-v", "ON_ERROR_STOP=1", "-c", sql],
        text=True,
        env=os.environ.copy(),
    ).strip()


assert psql("select count(*) from repair_audit") == "2"
assert psql("select string_agg(record_id, ',' order by record_id) from repair_audit") == ",".join(expected)
assert psql("select guard_state from descriptor_validation_cases where case_id='tenant_77_geo_archive_intentional_empty'") == "leave"
assert psql("select count(*) from repair_audit where record_id='tenant_77_geo_archive_intentional_empty'") == "0"
assert psql("select status || ':' || repaired_ids from incident_status where ticket='CRDB-63642'") == "recovered:tenant_31_orders_pk_swap,tenant_42_events_pk_swap"
print("artifact and db ok")
