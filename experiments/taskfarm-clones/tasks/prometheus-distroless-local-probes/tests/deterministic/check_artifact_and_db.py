import json
import os
import subprocess
from pathlib import Path


ARTIFACT = Path("/app/artifacts/prometheus_distroless_probe_repair.json")
EXPECTED = ["prom-ceems-primary", "prom-edge-rules"]
UNTOUCHED = ["prom-legacy-shell", "prom-public-metrics"]


def psql(sql):
    return subprocess.check_output(
        ["psql", "-X", "-q", "-t", "-A", "-v", "ON_ERROR_STOP=1", "-c", sql],
        text=True,
        env=os.environ.copy(),
    ).strip()


assert ARTIFACT.exists(), f"missing {ARTIFACT}"
data = json.loads(ARTIFACT.read_text())
for key in [
    "ticket_id",
    "incident_id",
    "affected_instances",
    "untouched_instances",
    "broad_workaround_rejected",
    "scope_note",
]:
    assert key in data, f"artifact missing {key}"
assert data["ticket_id"] == "PROMOP-8605", data
assert data["incident_id"] == "distroless-listenlocal-probes", data

found = sorted(item["instance_id"] for item in data["affected_instances"])
assert found == EXPECTED, found
for item in data["affected_instances"]:
    assert item["before_kind"] == "exec", item
    assert item["after_kind"] == "httpGet", item
    assert item["probe_path"] == "/-/ready", item
    assert item.get("evidence"), item

assert sorted(data["untouched_instances"]) == UNTOUCHED, data["untouched_instances"]
scope_words = (data["broad_workaround_rejected"] + " " + data["scope_note"]).lower()
assert "rollback" in scope_words or "rolling back" in scope_words or "fleet" in scope_words, scope_words
assert "only" in scope_words or "scoped" in scope_words, scope_words

assert psql("select count(*) from repair_audit") == "2"
assert psql("select string_agg(record_id, ',' order by record_id) from repair_audit") == ",".join(EXPECTED)
assert psql("select current_probe_kind || ':' || repair_action from probe_inventory where instance_id='prom-ceems-primary'") == "httpGet:switch-to-httpget"
assert psql("select current_probe_kind || ':' || repair_action from probe_inventory where instance_id='prom-edge-rules'") == "httpGet:switch-to-httpget"
assert psql("select current_probe_kind || ':' || repair_action from probe_inventory where instance_id='prom-legacy-shell'") == "exec:leave"
assert psql("select current_probe_kind || ':' || repair_action from probe_inventory where instance_id='prom-public-metrics'") == "httpGet:leave"
assert psql("select status || ':' || repaired_ids from incident_status where ticket='PROMOP-8605'") == "recovered:prom-ceems-primary,prom-edge-rules"
print("artifact and postgres ok")
